import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Article, Asset
from app.services.content import extract_image_sources, replace_image_sources
from app.services.wechat import wechat_client

logger = get_logger(__name__)


def _find_uploaded_body_image(
    db: Session, article_id: int, source_url: str
) -> Asset | None:
    return db.scalars(
        select(Asset)
        .where(
            Asset.article_id == article_id,
            Asset.asset_type == "body_image",
            Asset.source_url == source_url,
            Asset.status == "uploaded",
            Asset.wechat_url.is_not(None),
        )
        .order_by(Asset.created_at.desc())
    ).first()


async def upload_body_images(db: Session, article: Article) -> str:
    html = article.current_html or ""
    sources = extract_image_sources(html)
    replacements: dict[str, str] = {}
    failures: list[str] = []
    reused = 0
    for source in sources:
        if source.startswith("data:"):
            continue

        cached = _find_uploaded_body_image(db, article.id, source)
        if cached and cached.wechat_url:
            replacements[source] = cached.wechat_url
            reused += 1
            continue

        asset = Asset(article_id=article.id, source_url=source, asset_type="body_image", status="pending")
        db.add(asset)
        db.flush()
        try:
            local_path = await _materialize_image(source)
            wechat_url = await wechat_client.upload_article_image(local_path)
            asset.local_path = local_path
            asset.wechat_url = wechat_url
            asset.status = "uploaded"
            replacements[source] = wechat_url
        except Exception as exc:
            asset.status = "failed"
            asset.error = str(exc)
            failures.append(f"{source}: {exc}")
        finally:
            db.flush()

    if reused:
        logger.info(f"复用已上传的正文图片: article_id={article.id}, count={reused}")

    if replacements:
        article.current_html = replace_image_sources(html, replacements)
    db.commit()

    if failures:
        raise RuntimeError("正文图片上传微信失败：" + "；".join(failures[:3]))

    return article.current_html or html


async def upload_cover_image(db: Session, article_id: int | None, file_path: str) -> Asset:
    asset = Asset(
        article_id=article_id,
        source_url=file_path,
        local_path=file_path,
        asset_type="cover",
        status="pending",
    )
    db.add(asset)
    db.flush()
    try:
        asset.media_id = await wechat_client.upload_cover_material(file_path)
        asset.status = "uploaded"
    except Exception as exc:
        asset.status = "failed"
        asset.error = str(exc)
    db.commit()
    db.refresh(asset)
    return asset


async def _materialize_image(source: str) -> str:
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        suffix = Path(parsed.path).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(source)
            response.raise_for_status()
        Path(temp_path).write_bytes(response.content)
        return temp_path
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {source}")
    return str(path.resolve())
