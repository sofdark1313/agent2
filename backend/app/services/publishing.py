from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import PublishingError
from app.core.logging import get_logger
from app.models import Article, PublishJob
from app.services.assets import upload_body_images
from app.services.settings_store import get_public_setting
from app.services.wechat import WeChatApiError, wechat_client

logger = get_logger(__name__)


def _check_article_ready_for_publish(article: Article, action: str) -> None:
    """检查文章是否可以进行发布操作"""
    if article.status == "generating":
        raise PublishingError("文章仍在 AI 生成中，请生成完成后再操作。")
    if article.status == "failed":
        raise PublishingError(f"文章生成失败，不能{action}：{article.digest}")


def _check_idempotent_publish(db: Session, article_id: int, draft_media_id: str) -> PublishJob | None:
    """检查是否已经对同一草稿发起过发布，返回已存在的 job（如果有）"""
    existing = db.scalars(
        select(PublishJob).where(
            PublishJob.article_id == article_id,
            PublishJob.action == "publish",
            PublishJob.draft_media_id == draft_media_id,
            PublishJob.status.in_(["running", "publishing", "succeeded"]),
        )
    ).first()
    return existing


async def create_wechat_draft(db: Session, article: Article, thumb_media_id: str) -> PublishJob:
    logger.info(f"创建微信草稿: article_id={article.id}, thumb_media_id={thumb_media_id}")
    job = PublishJob(
        article_id=article.id,
        target="wechat",
        action="create_draft",
        status="running",
        request_payload={"thumb_media_id": thumb_media_id},
        response_payload={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        html = await upload_body_images(db, article)
        result = await wechat_client.create_draft(
            title=article.title,
            html=html,
            digest=article.digest,
            thumb_media_id=thumb_media_id,
            author=get_public_setting(db, "default_author"),
        )
        job.status = "succeeded"
        job.response_payload = result
        job.draft_media_id = result.get("media_id")
        article.status = "draft_created"
        logger.info(f"草稿创建成功: job_id={job.id}, draft_media_id={job.draft_media_id}")
    except WeChatApiError as exc:
        job.status = "failed"
        job.error = _friendly_wechat_error(str(exc))
        job.response_payload = exc.payload
        logger.error(f"草稿创建失败: job_id={job.id}, error={job.error}")
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.response_payload = {}
        logger.exception(f"草稿创建异常: job_id={job.id}")
    db.commit()
    db.refresh(job)
    return job


async def publish_wechat_article(db: Session, article: Article, media_id: str) -> PublishJob:
    logger.info(f"发布微信文章: article_id={article.id}, media_id={media_id}")

    # 状态保护：检查文章是否可以发布
    _check_article_ready_for_publish(article, "发布")

    # 早期短路：env 关闭时直接拒绝，不污染 PublishJob 表
    if not settings.wechat_auto_publish:
        raise PublishingError(
            "WECHAT_AUTO_PUBLISH 未开启。请在 .env 中设置 WECHAT_AUTO_PUBLISH=true 后重启后端，"
            "或仅创建草稿、由人工到公众号后台完成发布。"
        )

    # 幂等检查：同一草稿不能重复发布
    existing_job = _check_idempotent_publish(db, article.id, media_id)
    if existing_job:
        logger.info(f"发现已存在的发布任务: job_id={existing_job.id}, status={existing_job.status}")
        return existing_job

    job = PublishJob(
        article_id=article.id,
        target="wechat",
        action="publish",
        status="running",
        draft_media_id=media_id,
        request_payload={"media_id": media_id},
        response_payload={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = await wechat_client.publish(media_id)
        # freepublish/submit 是异步的，提交成功只代表任务已提交
        # 状态改为 publishing，等待轮询确认实际发布结果
        job.status = "publishing"
        job.response_payload = result
        job.publish_id = str(result.get("publish_id") or "")
        article.status = "publishing"  # 文章状态也改为 publishing，而非直接 published
    except WeChatApiError as exc:
        job.status = "failed"
        job.error = _friendly_wechat_error(str(exc))
        job.response_payload = exc.payload
    db.commit()
    db.refresh(job)
    return job


async def poll_publish_status(db: Session, job: PublishJob) -> PublishJob:
    """
    轮询微信发布状态，更新 job 和 article 状态。
    
    微信 freepublish/get 返回的 publish_status:
    - 0: 发布成功
    - 1: 发布中
    - 2: 原创失败（可继续群发）
    - 3: 常规失败（不可继续群发）
    - 4: 平台审核不通过
    - 5: 成功后用户删除
    - 6: 成功后系统封禁
    """
    if not job.publish_id:
        job.status = "failed"
        job.error = "缺少 publish_id，无法查询发布状态"
        db.commit()
        return job
    
    try:
        result = await wechat_client.get_publish_status(job.publish_id)
        job.response_payload = result
        
        publish_status = result.get("publish_status")
        
        if publish_status == 0:
            # 发布成功
            job.status = "succeeded"
            article = db.get(Article, job.article_id)
            if article:
                article.status = "published"
        elif publish_status == 1:
            # 仍在发布中，保持 publishing 状态
            job.status = "publishing"
        elif publish_status == 2:
            # 原创失败但可继续群发，视为成功
            job.status = "succeeded"
            job.error = "原创声明失败，但文章已发布"
            article = db.get(Article, job.article_id)
            if article:
                article.status = "published"
        else:
            # 3, 4, 5, 6 都是失败状态
            status_messages = {
                3: "发布失败",
                4: "平台审核不通过",
                5: "发布成功后被用户删除",
                6: "发布成功后被系统封禁",
            }
            job.status = "failed"
            job.error = status_messages.get(publish_status, f"未知发布状态: {publish_status}")
            article = db.get(Article, job.article_id)
            if article:
                article.status = "publish_failed"
                
    except WeChatApiError as exc:
        job.error = f"查询发布状态失败: {exc}"
        # 查询失败不改变 job 状态，保持 publishing 以便重试
        job.response_payload = exc.payload
    except Exception as exc:
        job.error = f"查询发布状态异常: {exc}"
    
    db.commit()
    db.refresh(job)
    return job


async def poll_all_publishing_jobs(db: Session) -> list[PublishJob]:
    """轮询所有处于 publishing 状态的 job，更新其状态"""
    publishing_jobs = list(db.scalars(
        select(PublishJob).where(PublishJob.status == "publishing")
    ).all())
    
    results = []
    for job in publishing_jobs:
        updated_job = await poll_publish_status(db, job)
        results.append(updated_job)
    
    return results


async def publish_pipeline(
    db: Session,
    article: Article,
    cover_path: str | None = None,
    thumb_media_id: str | None = None,
) -> dict:
    """
    端到端发布 pipeline：
    1. 如果提供了 cover_path，上传封面获取 thumb_media_id
    2. 创建草稿
    3. 提交发布

    返回包含各步骤结果的字典。

    注意：PublishingError（业务校验失败）会原样抛出，由 API 层翻译成 HTTP 409；
    其他异常被吞进 result["error"] 以便前端展示进度时间线。
    """
    from app.services.assets import upload_cover_image

    # 状态保护（让 PublishingError 抛出去，不进 result["error"]）
    _check_article_ready_for_publish(article, "发布")

    result = {
        "cover_asset": None,
        "draft_job": None,
        "publish_job": None,
        "error": None,
        "stage": "init",
    }

    try:
        # Step 1: 上传封面（如果需要）
        if cover_path and not thumb_media_id:
            result["stage"] = "upload_cover"
            cover_asset = await upload_cover_image(db, article.id, cover_path)
            result["cover_asset"] = cover_asset
            if cover_asset.status == "failed":
                result["error"] = f"封面上传失败：{cover_asset.error}"
                return result
            thumb_media_id = cover_asset.media_id

        if not thumb_media_id:
            result["error"] = "缺少封面素材 media_id"
            return result

        # Step 2: 创建草稿
        result["stage"] = "create_draft"
        draft_job = await create_wechat_draft(db, article, thumb_media_id)
        result["draft_job"] = draft_job
        if draft_job.status == "failed":
            result["error"] = f"创建草稿失败：{draft_job.error}"
            return result

        draft_media_id = draft_job.draft_media_id
        if not draft_media_id:
            result["error"] = "创建草稿成功但未返回 draft_media_id"
            return result

        # Step 3: 提交发布
        result["stage"] = "publish"
        try:
            publish_job = await publish_wechat_article(db, article, draft_media_id)
        except PublishingError as exc:
            # auto_publish 关闭等业务态：草稿已建好，pipeline 收尾在 draft_created
            result["stage"] = "draft_created"
            result["error"] = str(exc)
            return result

        result["publish_job"] = publish_job
        if publish_job.status == "failed":
            result["error"] = f"提交发布失败：{publish_job.error}"
            return result

        result["stage"] = "completed"
        return result

    except PublishingError:
        raise
    except Exception as exc:
        logger.exception(f"publish_pipeline 异常: article_id={article.id}")
        result["error"] = str(exc)
        return result


def _friendly_wechat_error(message: str) -> str:
    if "40007" in message or "invalid media_id" in message:
        return (
            "微信返回 invalid media_id。创建草稿需要封面永久素材 thumb_media_id，"
            "请先上传封面素材，不要填写草稿 media_id 或正文图片 URL。原始错误："
            + message
        )
    if "48001" in message or "api unauthorized" in message.lower():
        return (
            "微信返回 48001：当前公众号没有调用『发表/freepublish』接口的权限。"
            "通常因为：① 公众号未通过微信认证；② 是个人订阅号（不开放发表接口）；"
            "③ 已认证账号的接口权限尚未生效。\n"
            "解决方案：在 .env 中设置 WECHAT_AUTO_PUBLISH=false 后重启后端，"
            "改为只创建草稿，由人工到公众号后台『草稿箱』点群发即可。"
            "原始错误：" + message
        )
    if "40164" in message or "invalid ip" in message.lower():
        return (
            "微信返回 40164：当前服务器 IP 不在公众号 IP 白名单内。"
            "请到公众号后台 → 设置与开发 → 基本配置 → IP 白名单，把后端的出口 IP 加进去。"
            "原始错误：" + message
        )
    if "40001" in message or "invalid credential" in message.lower():
        return (
            "微信返回 40001：access_token 无效或 AppSecret 错误。"
            "请核对 .env 里的 WECHAT_APP_ID / WECHAT_APP_SECRET。"
            "原始错误：" + message
        )
    if "45009" in message or "out of api" in message.lower():
        return (
            "微信返回 45009：接口调用次数已达上限（freepublish/submit 每日 100 次，"
            "draft/add 每日 100 次）。请等次日恢复或精简发布频率。原始错误：" + message
        )
    return message
