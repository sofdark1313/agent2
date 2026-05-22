from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Article

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
    with SessionLocal() as db:
        interrupted = db.query(Article).filter(Article.status == "generating").all()
        for article in interrupted:
            article.status = "failed"
            article.digest = "上次 AI 生成任务被中断，请点击重新润色或重新创建文章。"
        if interrupted:
            db.commit()
