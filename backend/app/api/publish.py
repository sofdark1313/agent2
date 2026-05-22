from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Article, PublishJob
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
    return await upload_cover_image(db, article_id, str(destination.resolve()))


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
        if not thumb_media_id:
            raise HTTPException(status_code=400, detail="thumb_media_id is required")
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
