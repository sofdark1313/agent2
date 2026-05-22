from fastapi import APIRouter

from app.api import articles, health, publish, settings

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(publish.router, prefix="/publish", tags=["publish"])
