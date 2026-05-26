from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import SessionLocal
from app.models import Article

# 初始化日志
setup_logging()
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def recover_interrupted_generation_tasks() -> None:
    """恢复被中断的生成任务"""
    logger.info("应用启动，检查被中断的生成任务...")
    with SessionLocal() as db:
        interrupted = db.query(Article).filter(Article.status == "generating").all()
        for article in interrupted:
            article.status = "failed"
            article.digest = "上次 AI 生成任务被中断，请点击重新润色或重新创建文章。"
            logger.warning(f"恢复被中断的文章: article_id={article.id}, title={article.title}")
        if interrupted:
            db.commit()
            logger.info(f"已恢复 {len(interrupted)} 个被中断的生成任务")
    logger.info(f"{settings.app_name} 启动完成")
