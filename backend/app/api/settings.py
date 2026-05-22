from fastapi import APIRouter

from app.core.config import settings
from app.schemas import PreflightOut
from app.services.ai import AiService
from app.services.wechat import wechat_client

router = APIRouter()


@router.get("/status")
async def settings_status() -> dict[str, object]:
    wechat = await wechat_client.preflight()
    return {
        "openai_configured": AiService().is_configured(),
        "openai_model": settings.openai_model,
        "wechat": wechat,
    }


@router.get("/wechat/preflight", response_model=PreflightOut)
async def wechat_preflight() -> PreflightOut:
    return PreflightOut(**await wechat_client.preflight())
