from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Article, Revision
from app.schemas import (
    ArticleCreateFromMarkdown,
    ArticleCreateFromTopic,
    ArticleGenerateRequest,
    ArticleOut,
    RevisionOut,
)
from app.services.ai import AiService
from app.services.content import apply_wechat_style, markdown_to_html

router = APIRouter()


@router.get("", response_model=list[ArticleOut])
def list_articles(db: Session = Depends(get_db)) -> list[Article]:
    return list(db.scalars(select(Article).order_by(desc(Article.created_at))).all())


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)) -> Article:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("/from-markdown", response_model=ArticleOut)
def create_from_markdown(payload: ArticleCreateFromMarkdown, db: Session = Depends(get_db)) -> Article:
    ai_result = AiService().polish_markdown(payload.markdown, payload.instruction)
    title = payload.title or ai_result.title
    article = Article(
        title=title,
        source_type="markdown",
        source_markdown=payload.markdown,
        current_html=ai_result.html,
        digest=ai_result.digest,
        cover_prompt=ai_result.cover_prompt,
        tags=ai_result.tags,
        status="generated",
    )
    db.add(article)
    db.flush()
    db.add(
        Revision(
            article_id=article.id,
            kind="ai_polish",
            instruction=payload.instruction,
            title=title,
            digest=ai_result.digest,
            html=ai_result.html,
            ai_payload=ai_result.model_dump(),
        )
    )
    db.commit()
    db.refresh(article)
    return article


@router.post("/from-topic", response_model=ArticleOut)
def create_from_topic(payload: ArticleCreateFromTopic, db: Session = Depends(get_db)) -> Article:
    ai_result = AiService().generate_from_topic(
        payload.topic, payload.audience, payload.style, payload.word_count
    )
    article = Article(
        title=ai_result.title,
        source_type="topic",
        topic_prompt=payload.model_dump_json(),
        current_html=ai_result.html,
        digest=ai_result.digest,
        cover_prompt=ai_result.cover_prompt,
        tags=ai_result.tags,
        status="generated",
    )
    db.add(article)
    db.flush()
    db.add(
        Revision(
            article_id=article.id,
            kind="ai_generate",
            instruction=payload.topic,
            title=ai_result.title,
            digest=ai_result.digest,
            html=ai_result.html,
            ai_payload=ai_result.model_dump(),
        )
    )
    db.commit()
    db.refresh(article)
    return article


@router.post("/{article_id}/regenerate", response_model=ArticleOut)
def regenerate_article(
    article_id: int, payload: ArticleGenerateRequest, db: Session = Depends(get_db)
) -> Article:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    source = article.source_markdown or article.current_html or ""
    ai_result = AiService().polish_markdown(source, payload.instruction)
    article.title = ai_result.title
    article.current_html = ai_result.html
    article.digest = ai_result.digest
    article.cover_prompt = ai_result.cover_prompt
    article.tags = ai_result.tags
    article.status = "generated"
    db.add(
        Revision(
            article_id=article.id,
            kind="ai_regenerate",
            instruction=payload.instruction,
            title=ai_result.title,
            digest=ai_result.digest,
            html=ai_result.html,
            ai_payload=ai_result.model_dump(),
        )
    )
    db.commit()
    db.refresh(article)
    return article


@router.post("/preview-markdown")
def preview_markdown(payload: ArticleCreateFromMarkdown) -> dict[str, str]:
    html = apply_wechat_style(markdown_to_html(payload.markdown))
    return {"html": html}


@router.get("/{article_id}/revisions", response_model=list[RevisionOut])
def list_revisions(article_id: int, db: Session = Depends(get_db)) -> list[Revision]:
    return list(
        db.scalars(
            select(Revision)
            .where(Revision.article_id == article_id)
            .order_by(desc(Revision.created_at))
        ).all()
    )
