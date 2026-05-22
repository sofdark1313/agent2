from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Article, PublishJob
from app.services.assets import upload_body_images
from app.services.settings_store import get_public_setting
from app.services.wechat import WeChatApiError, wechat_client


async def create_wechat_draft(db: Session, article: Article, thumb_media_id: str) -> PublishJob:
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
    except WeChatApiError as exc:
        job.status = "failed"
        job.error = _friendly_wechat_error(str(exc))
        job.response_payload = exc.payload
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.response_payload = {}
    db.commit()
    db.refresh(job)
    return job


async def publish_wechat_article(db: Session, article: Article, media_id: str) -> PublishJob:
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
        if not settings.wechat_auto_publish:
            raise WeChatApiError("WECHAT_AUTO_PUBLISH 未开启")
        result = await wechat_client.publish(media_id)
        job.status = "succeeded"
        job.response_payload = result
        job.publish_id = str(result.get("publish_id") or "")
        article.status = "published"
    except WeChatApiError as exc:
        job.status = "failed"
        job.error = _friendly_wechat_error(str(exc))
        job.response_payload = exc.payload
    db.commit()
    db.refresh(job)
    return job


def _friendly_wechat_error(message: str) -> str:
    if "40007" in message or "invalid media_id" in message:
        return (
            "微信返回 invalid media_id。创建草稿需要封面永久素材 thumb_media_id，"
            "请先上传封面素材，不要填写草稿 media_id 或正文图片 URL。原始错误："
            + message
        )
    return message
