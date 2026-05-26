from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import guess_title_from_markdown
from app.db.session import SessionLocal, get_db
from app.models import Article, Asset, PublishJob, Revision
from app.schemas import (
    ArticleCreateFromMarkdown,
    ArticleCreateFromTopic,
    ArticleGenerateRequest,
    ArticleOut,
    PaginatedResponse,
    PaginationParams,
    RevisionOut,
    SuccessResponse,
)
from app.services.ai import AiService
from app.services.background import run_in_background
from app.services.content import apply_wechat_style, markdown_to_html

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=PaginatedResponse[ArticleOut])
def list_articles(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ArticleOut]:
    """获取文章列表（分页）"""
    params = PaginationParams(page=page, page_size=page_size)
    
    query = select(Article)
    count_query = select(func.count(Article.id))
    
    if status:
        query = query.where(Article.status == status)
        count_query = count_query.where(Article.status == status)
    
    total = db.scalar(count_query) or 0
    items = list(
        db.scalars(
            query.order_by(desc(Article.created_at))
            .offset(params.offset)
            .limit(params.page_size)
        ).all()
    )
    
    return PaginatedResponse.create(
        items=[ArticleOut.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)) -> Article:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.delete("/{article_id}", response_model=SuccessResponse)
def delete_article(article_id: int, db: Session = Depends(get_db)) -> SuccessResponse:
    """删除文章及其关联数据"""
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    logger.info(f"删除文章: article_id={article_id}, title={article.title}")
    
    db.query(PublishJob).filter(PublishJob.article_id == article_id).delete(
        synchronize_session=False
    )
    db.query(Asset).filter(Asset.article_id == article_id).delete(synchronize_session=False)
    db.query(Revision).filter(Revision.article_id == article_id).delete(synchronize_session=False)
    db.delete(article)
    db.commit()
    
    return SuccessResponse(message=f"文章 {article_id} 已删除")


@router.post("/from-markdown", response_model=ArticleOut)
def create_from_markdown(payload: ArticleCreateFromMarkdown, db: Session = Depends(get_db)) -> Article:
    """从 Markdown 创建文章"""
    html = apply_wechat_style(markdown_to_html(payload.markdown))
    title = payload.title or guess_title_from_markdown(payload.markdown)
    
    logger.info(f"从 Markdown 创建文章: title={title}")
    
    article = Article(
        title=title,
        source_type="markdown",
        source_markdown=payload.markdown,
        current_html=html,
        digest="Markdown 已转换为公众号文章，可直接创建草稿。",
        cover_prompt=None,
        tags=[],
        status="generated",
    )
    db.add(article)
    db.flush()
    db.add(
        Revision(
            article_id=article.id,
            kind="markdown_convert",
            instruction=payload.instruction,
            title=title,
            digest=article.digest,
            html=html,
            ai_payload={"mode": "local_markdown_convert"},
        )
    )
    db.commit()
    db.refresh(article)
    return article


@router.post("/{article_id}/format", response_model=ArticleOut)
def format_article(article_id: int, db: Session = Depends(get_db)) -> Article:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.source_markdown:
        html = apply_wechat_style(markdown_to_html(article.source_markdown))
    else:
        html = apply_wechat_style(article.current_html or "")
    article.current_html = html
    if not article.digest:
        article.digest = "文章已重新排版。"
    if article.status not in ("generating", "failed"):
        article.status = "generated"
    db.add(
        Revision(
            article_id=article.id,
            kind="format",
            instruction="重新应用公众号排版",
            title=article.title,
            digest=article.digest,
            html=html,
            ai_payload={"mode": "local_format"},
        )
    )
    db.commit()
    db.refresh(article)
    return article


@router.post("/from-topic", response_model=ArticleOut)
def create_from_topic(payload: ArticleCreateFromTopic, db: Session = Depends(get_db)) -> Article:
    """从主题创建文章（AI 生成）"""
    logger.info(f"从主题创建文章: topic={payload.topic}")
    
    article = Article(
        title=f"生成中：{payload.topic[:40]}",
        source_type="topic",
        topic_prompt=payload.model_dump_json(),
        current_html="<p>AI 正在生成文章，请稍候刷新。</p>",
        digest="AI 正在生成文章，请稍候刷新。",
        cover_prompt=None,
        tags=[],
        status="generating",
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    run_in_background(
        _finish_topic_article,
        article.id,
        payload.topic,
        payload.audience,
        payload.style,
        payload.word_count,
        name=f"finish_topic_article:{article.id}",
    )
    return article


@router.post("/{article_id}/regenerate", response_model=ArticleOut)
def regenerate_article(
    article_id: int, payload: ArticleGenerateRequest, db: Session = Depends(get_db)
) -> Article:
    """重新生成文章（AI 润色）"""
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    logger.info(f"重新生成文章: article_id={article_id}, instruction={payload.instruction[:50]}...")

    source = article.source_markdown or article.current_html or ""
    previous = {
        "title": article.title,
        "html": article.current_html,
        "digest": article.digest,
        "cover_prompt": article.cover_prompt,
        "tags": article.tags,
        "status": article.status,
    }
    article.status = "generating"
    article.digest = "AI 正在重新润色，请稍候刷新。"
    db.commit()
    db.refresh(article)
    run_in_background(
        _finish_regenerate_article,
        article.id,
        source,
        payload.instruction,
        previous,
        name=f"finish_regenerate_article:{article.id}",
    )
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


def _run_in_background(func, *args) -> None:
    """在后台线程中运行函数"""
    thread = Thread(target=func, args=args, daemon=True)
    thread.start()


def _finish_topic_article(
    article_id: int,
    topic: str,
    audience: str | None,
    style: str | None,
    word_count: int | None,
) -> None:
    """后台任务：完成主题文章生成"""
    logger.info(f"开始生成主题文章: article_id={article_id}, topic={topic}")
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)
        if not article:
            logger.warning(f"文章不存在: article_id={article_id}")
            return
        try:
            ai_result = AiService().generate_from_topic(topic, audience, style, word_count)
            article.title = ai_result.title
            article.current_html = ai_result.html
            article.digest = ai_result.digest
            article.cover_prompt = ai_result.cover_prompt
            article.tags = ai_result.tags
            article.status = "generated"
            db.add(
                Revision(
                    article_id=article.id,
                    kind="ai_generate",
                    instruction=topic,
                    title=ai_result.title,
                    digest=ai_result.digest,
                    html=ai_result.html,
                    ai_payload=ai_result.model_dump(),
                )
            )
            logger.info(f"主题文章生成成功: article_id={article_id}, title={ai_result.title}")
        except Exception as exc:
            article.status = "failed"
            article.digest = str(exc)
            logger.exception(f"主题文章生成失败: article_id={article_id}")
        db.commit()
    finally:
        db.close()


def _finish_regenerate_article(
    article_id: int, source: str, instruction: str, previous: dict | None = None
) -> None:
    """后台任务：完成文章重新生成"""
    logger.info(f"开始重新生成文章: article_id={article_id}")
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)
        if not article:
            logger.warning(f"文章不存在: article_id={article_id}")
            return
        try:
            ai_result = AiService().polish_markdown(source, instruction)
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
                    instruction=instruction,
                    title=ai_result.title,
                    digest=ai_result.digest,
                    html=ai_result.html,
                    ai_payload=ai_result.model_dump(),
                )
            )
            logger.info(f"文章重新生成成功: article_id={article_id}, title={ai_result.title}")
        except Exception as exc:
            if previous:
                article.title = previous.get("title") or article.title
                article.current_html = previous.get("html") or article.current_html
                article.cover_prompt = previous.get("cover_prompt")
                article.tags = previous.get("tags") or []
                article.status = previous.get("status") or "generated"
                article.digest = (
                    "AI 润色失败，已保留原文章内容。错误："
                    + str(exc)
                )
            else:
                article.status = "failed"
                article.digest = str(exc)
            logger.exception(f"文章重新生成失败: article_id={article_id}")
        db.commit()
    finally:
        db.close()
