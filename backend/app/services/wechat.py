import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

WECHAT_API = "https://api.weixin.qq.com"


class WeChatApiError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


class WeChatClient:
    def __init__(self) -> None:
        self._access_token: str | None = None
        self._expires_at = 0.0

    def is_configured(self) -> bool:
        return bool(settings.wechat_app_id and settings.wechat_app_secret)

    async def preflight(self) -> dict[str, Any]:
        checks = {
            "app_id": bool(settings.wechat_app_id),
            "app_secret": bool(settings.wechat_app_secret),
            "auto_publish_enabled": settings.wechat_auto_publish,
        }
        if not checks["app_id"] or not checks["app_secret"]:
            return {"ok": False, "checks": checks, "message": "缺少 WECHAT_APP_ID 或 WECHAT_APP_SECRET"}
        try:
            await self.get_access_token()
        except Exception as exc:
            return {"ok": False, "checks": checks, "message": f"微信 token 获取失败: {exc}"}
        return {"ok": True, "checks": checks, "message": "微信接口配置可用"}

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 300:
            return self._access_token
        if not self.is_configured():
            raise WeChatApiError("微信 AppID/AppSecret 未配置")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{WECHAT_API}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": settings.wechat_app_id,
                    "secret": settings.wechat_app_secret,
                },
            )
        payload = response.json()
        self._raise_for_wechat_error(payload)
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + int(payload.get("expires_in", 7200))
        return self._access_token

    async def upload_article_image(self, image_path: str) -> str:
        token = await self.get_access_token()
        path = Path(image_path)
        if not path.exists():
            raise WeChatApiError(f"图片不存在: {image_path}")
        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as image:
                response = await client.post(
                    f"{WECHAT_API}/cgi-bin/media/uploadimg",
                    params={"access_token": token},
                    files={"media": (path.name, image, "application/octet-stream")},
                )
        payload = response.json()
        self._raise_for_wechat_error(payload)
        return payload["url"]

    async def upload_cover_material(self, image_path: str) -> str:
        token = await self.get_access_token()
        path = Path(image_path)
        if not path.exists():
            raise WeChatApiError(f"封面图片不存在: {image_path}")
        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as image:
                response = await client.post(
                    f"{WECHAT_API}/cgi-bin/material/add_material",
                    params={"access_token": token, "type": "thumb"},
                    files={"media": (path.name, image, "application/octet-stream")},
                )
        payload = response.json()
        self._raise_for_wechat_error(payload)
        return payload["media_id"]

    async def create_draft(
        self,
        *,
        title: str,
        html: str,
        digest: str | None,
        thumb_media_id: str,
        author: str | None = None,
    ) -> dict[str, Any]:
        token = await self.get_access_token()
        payload = {
            "articles": [
                {
                    "title": title,
                    "author": author or "",
                    "digest": digest or "",
                    "content": html,
                    "content_source_url": "",
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{WECHAT_API}/cgi-bin/draft/add",
                params={"access_token": token},
                json=payload,
            )
        result = response.json()
        self._raise_for_wechat_error(result)
        return result

    async def publish(self, media_id: str) -> dict[str, Any]:
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{WECHAT_API}/cgi-bin/freepublish/submit",
                params={"access_token": token},
                json={"media_id": media_id},
            )
        result = response.json()
        self._raise_for_wechat_error(result)
        return result

    async def get_publish_status(self, publish_id: str) -> dict[str, Any]:
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{WECHAT_API}/cgi-bin/freepublish/get",
                params={"access_token": token},
                json={"publish_id": publish_id},
            )
        result = response.json()
        self._raise_for_wechat_error(result)
        return result

    def _raise_for_wechat_error(self, payload: dict[str, Any]) -> None:
        errcode = payload.get("errcode")
        if errcode not in (None, 0):
            errmsg = payload.get("errmsg", "unknown wechat error")
            raise WeChatApiError(f"微信接口错误 {errcode}: {errmsg}", payload)


wechat_client = WeChatClient()
