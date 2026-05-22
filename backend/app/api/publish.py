from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Article, Asset, PublishJob
from app.schemas import AssetOut, PublishJobOut, PublishRequest
from app.services.assets import upload_cover_image
from app.services.publishing import create_wechat_draft, publish_wechat_article

router = APIRouter()


@router.get("/jobs", response_model=list[PublishJobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[PublishJob]:
    return list(db.scalars(select(PublishJob).order_by(desc(PublishJob.created_at))).all())


@router.post("/cover", response_model=AssetOut)
async def upload_cover(
    file: UploadFile = File(...),
    article_id: int | None = None,
    db: Session = Depends(get_db),
):
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    destination = upload_dir / (file.filename or "cover.jpg")
    content = await file.read()
    destination.write_bytes(content)
    asset = await upload_cover_image(db, article_id, str(destination.resolve()))
    if asset.status == "failed":
        raise HTTPException(status_code=502, detail=f"封面上传微信失败：{asset.error}")
    return asset


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
    if not draft_media_id:
        latest = db.scalars(
            select(PublishJob)
            .where(PublishJob.article_id == article_id, PublishJob.action == "create_draft")
            .order_by(desc(PublishJob.created_at))
        ).first()
        draft_media_id = latest.draft_media_id if latest else None
    if not draft_media_id:
        raise HTTPException(status_code=400, detail="draft_media_id is required")
    return await publish_wechat_article(db, article, draft_media_id)
