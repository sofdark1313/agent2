from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas import PreflightOut, PublicSettingsOut
from app.services.ai import AiProviderError, AiService
from app.services.settings_store import get_public_settings, update_public_settings
from app.services.wechat import wechat_client

router = APIRouter()


@router.get("/status")
async def settings_status(db: Session = Depends(get_db)) -> dict[str, object]:
    wechat = await wechat_client.preflight()
    return {
        "ai_configured": AiService().is_configured(),
        "ai_model_name": settings.ai_model_name,
        "ai_base_url_configured": bool(settings.ai_base_url),
        "wechat": wechat,
        "account": get_public_settings(db),
    }


@router.get("/wechat/preflight", response_model=PreflightOut)
async def wechat_preflight() -> PreflightOut:
    return PreflightOut(**await wechat_client.preflight())


@router.get("/ai/test")
def ai_test() -> dict[str, object]:
    try:
        return AiService().test_connection()
    except AiProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/app", response_model=PublicSettingsOut)
def get_app_settings(db: Session = Depends(get_db)) -> PublicSettingsOut:
    return PublicSettingsOut(**get_public_settings(db))


@router.put("/app", response_model=PublicSettingsOut)
def save_app_settings(payload: PublicSettingsOut, db: Session = Depends(get_db)) -> PublicSettingsOut:
    return PublicSettingsOut(**update_public_settings(db, payload.model_dump()))
