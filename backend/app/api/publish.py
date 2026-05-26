from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import FileValidationError, PublishingError
from app.core.files import save_upload_file
from app.core.logging import get_logger
from app.db.session import get_db
from app.models import Article, Asset, PublishJob
from app.schemas import (
    AssetOut,
    PaginatedResponse,
    PaginationParams,
    PublishJobOut,
    PublishPipelineOut,
    PublishPipelineRequest,
    PublishRequest,
)
from app.services.assets import upload_cover_image
from app.services.publishing import (
    create_wechat_draft,
    poll_all_publishing_jobs,
    poll_publish_status,
    publish_pipeline,
    publish_wechat_article,
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/jobs", response_model=PaginatedResponse[PublishJobOut])
def list_jobs(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PublishJobOut]:
    """获取发布任务列表（分页）"""
    params = PaginationParams(page=page, page_size=page_size)
    
    total = db.scalar(select(func.count(PublishJob.id))) or 0
    items = list(
        db.scalars(
            select(PublishJob)
            .order_by(desc(PublishJob.created_at))
            .offset(params.offset)
            .limit(params.page_size)
        ).all()
    )
    
    return PaginatedResponse.create(
        items=[PublishJobOut.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/cover", response_model=AssetOut)
async def upload_cover(
    file: UploadFile = File(...),
    article_id: int | None = None,
    db: Session = Depends(get_db),
):
    """上传封面图片"""
    try:
        upload_dir = Path("uploads")
        destination = await save_upload_file(file, upload_dir)
        asset = await upload_cover_image(db, article_id, str(destination.resolve()))
        if asset.status == "failed":
            raise HTTPException(status_code=502, detail=f"封面上传微信失败：{asset.error}")
        return asset
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/articles/{article_id}", response_model=PublishJobOut)
async def publish_article(
    article_id: int,
    payload: PublishRequest,
    thumb_media_id: str | None = None,
    draft_media_id: str | None = None,
    db: Session = Depends(get_db),
) -> PublishJob:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        if payload.action == "create_draft":
            if article.status == "generating":
                raise HTTPException(status_code=409, detail="文章仍在 AI 生成中，请生成完成后再创建草稿。")
            if article.status == "failed":
                raise HTTPException(status_code=409, detail=f"文章生成失败，不能创建草稿：{article.digest}")
            if not thumb_media_id:
                latest_cover = db.scalars(
                    select(Asset)
                    .where(
                        Asset.article_id == article_id,
                        Asset.asset_type == "cover",
                        Asset.status == "uploaded",
                        Asset.media_id.is_not(None),
                    )
                    .order_by(desc(Asset.created_at))
                ).first()
                thumb_media_id = latest_cover.media_id if latest_cover else None
            if not thumb_media_id:
                raise HTTPException(
                    status_code=400,
                    detail="缺少封面素材 media_id。请先在右侧上传封面素材，或填写微信封面永久素材 thumb_media_id。",
                )
            return await create_wechat_draft(db, article, thumb_media_id)

        # action == "publish"
        if article.status == "generating":
            raise HTTPException(status_code=409, detail="文章仍在 AI 生成中，请生成完成后再发布。")
        if article.status == "failed":
            raise HTTPException(status_code=409, detail=f"文章生成失败，不能发布：{article.digest}")
        if article.status == "publishing":
            raise HTTPException(
                status_code=409,
                detail="文章正在发布中，请稍后通过『刷新发布状态』查看结果，避免重复提交。",
            )
        if not draft_media_id:
            latest = db.scalars(
                select(PublishJob)
                .where(PublishJob.article_id == article_id, PublishJob.action == "create_draft")
                .order_by(desc(PublishJob.created_at))
            ).first()
            draft_media_id = latest.draft_media_id if latest else None
        if not draft_media_id:
            raise HTTPException(
                status_code=400,
                detail="缺少 draft_media_id：请先成功创建草稿，再点击发布。",
            )
        return await publish_wechat_article(db, article, draft_media_id)

    except PublishingError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/jobs/{job_id}/poll", response_model=PublishJobOut)
async def poll_job_status(
    job_id: int,
    db: Session = Depends(get_db),
) -> PublishJob:
    """轮询单个发布任务的状态"""
    job = db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PublishJob not found")
    if job.action != "publish":
        raise HTTPException(status_code=400, detail="只能轮询 publish 类型的任务")
    if job.status not in ("publishing", "running"):
        # 已经是终态，直接返回
        return job
    return await poll_publish_status(db, job)


@router.post("/jobs/poll-all", response_model=list[PublishJobOut])
async def poll_all_jobs(
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    """轮询所有处于 publishing 状态的任务"""
    return await poll_all_publishing_jobs(db)


@router.post("/articles/{article_id}/pipeline", response_model=PublishPipelineOut)
async def publish_article_pipeline(
    article_id: int,
    payload: PublishPipelineRequest | None = None,
    file: UploadFile | None = File(default=None),
    payload_form: str | None = Form(default=None, alias="payload"),
    db: Session = Depends(get_db),
):
    """
    一键发布 pipeline：上传封面 → 创建草稿 → 提交发布

    可以通过以下方式提供封面：
    1. 上传封面文件 (file 参数)
    2. 提供已有的 thumb_media_id
    3. 使用文章已关联的最新封面素材

    支持两种调用方式：
    - JSON body: `{"thumb_media_id": "..."}`
    - multipart/form-data: `file` + 可选的 `payload` 字段（JSON 字符串）
    """
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # 同时兼容 JSON body 和 multipart 里的 payload 字段
    thumb_media_id: str | None = None
    if payload is not None:
        thumb_media_id = payload.thumb_media_id
    elif payload_form:
        try:
            import json as _json

            parsed = PublishPipelineRequest.model_validate(_json.loads(payload_form))
            thumb_media_id = parsed.thumb_media_id
        except Exception as exc:
            logger.warning(f"无法解析 multipart payload 字段: {exc}")

    cover_path = None

    # 如果上传了封面文件
    if file:
        try:
            upload_dir = Path("uploads")
            destination = await save_upload_file(file, upload_dir)
            cover_path = str(destination.resolve())
        except FileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # 如果没有提供封面，尝试使用已有的封面素材
    if not thumb_media_id and not cover_path:
        latest_cover = db.scalars(
            select(Asset)
            .where(
                Asset.article_id == article_id,
                Asset.asset_type == "cover",
                Asset.status == "uploaded",
                Asset.media_id.is_not(None),
            )
            .order_by(desc(Asset.created_at))
        ).first()
        if latest_cover:
            thumb_media_id = latest_cover.media_id

    if not thumb_media_id and not cover_path:
        raise HTTPException(
            status_code=400,
            detail="缺少封面。请上传封面文件、提供 thumb_media_id，或先为文章上传封面素材。",
        )

    try:
        result = await publish_pipeline(db, article, cover_path, thumb_media_id)

        # 转换为响应格式
        return PublishPipelineOut(
            cover_asset=AssetOut.model_validate(result["cover_asset"]) if result["cover_asset"] else None,
            draft_job=PublishJobOut.model_validate(result["draft_job"]) if result["draft_job"] else None,
            publish_job=PublishJobOut.model_validate(result["publish_job"]) if result["publish_job"] else None,
            error=result["error"],
            stage=result["stage"],
        )
    except PublishingError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
