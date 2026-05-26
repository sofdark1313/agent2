import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import WeChatError
from app.core.logging import get_logger

WECHAT_API = "https://api.weixin.qq.com"

logger = get_logger(__name__)


# 保留旧的异常名称以保持向后兼容
WeChatApiError = WeChatError


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
            logger.error(f"微信 token 获取失败: {exc}")
            return {"ok": False, "checks": checks, "message": f"微信 token 获取失败: {exc}"}
        return {"ok": True, "checks": checks, "message": "微信接口配置可用"}

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 300:
            return self._access_token
        if not self.is_configured():
            raise WeChatError("微信 AppID/AppSecret 未配置")
        
        logger.info("正在获取微信 access_token")
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
        logger.info("微信 access_token 获取成功")
        return self._access_token

    async def upload_article_image(self, image_path: str) -> str:
        logger.info(f"上传正文图片: {image_path}")
        token = await self.get_access_token()
        path = Path(image_path)
        if not path.exists():
            raise WeChatError(f"图片不存在: {image_path}")
        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as image:
                response = await client.post(
                    f"{WECHAT_API}/cgi-bin/media/uploadimg",
                    params={"access_token": token},
                    files={"media": (path.name, image, "application/octet-stream")},
                )
        payload = response.json()
        self._raise_for_wechat_error(payload)
        logger.info(f"正文图片上传成功: {payload.get('url', '')[:50]}...")
        return payload["url"]

    async def upload_cover_material(self, image_path: str) -> str:
        logger.info(f"上传封面素材: {image_path}")
        token = await self.get_access_token()
        path = Path(image_path)
        if not path.exists():
            raise WeChatError(f"封面图片不存在: {image_path}")
        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as image:
                response = await client.post(
                    f"{WECHAT_API}/cgi-bin/material/add_material",
                    params={"access_token": token, "type": "thumb"},
                    files={"media": (path.name, image, "application/octet-stream")},
                )
        payload = response.json()
        self._raise_for_wechat_error(payload)
        media_id = payload["media_id"]
        logger.info(f"封面素材上传成功: media_id={media_id}")
        return media_id

    async def create_draft(
        self,
        *,
        title: str,
        html: str,
        digest: str | None,
        thumb_media_id: str,
        author: str | None = None,
    ) -> dict[str, Any]:
        logger.info(f"创建草稿: title={title}")
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
        logger.info(f"草稿创建成功: media_id={result.get('media_id')}")
        return result

    async def publish(self, media_id: str) -> dict[str, Any]:
        logger.info(f"提交发布: media_id={media_id}")
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{WECHAT_API}/cgi-bin/freepublish/submit",
                params={"access_token": token},
                json={"media_id": media_id},
            )
        result = response.json()
        self._raise_for_wechat_error(result)
        logger.info(f"发布提交成功: publish_id={result.get('publish_id')}")
        return result

    async def get_publish_status(self, publish_id: str) -> dict[str, Any]:
        logger.debug(f"查询发布状态: publish_id={publish_id}")
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{WECHAT_API}/cgi-bin/freepublish/get",
                params={"access_token": token},
                json={"publish_id": publish_id},
            )
        result = response.json()
        self._raise_for_wechat_error(result)
        logger.debug(f"发布状态: publish_status={result.get('publish_status')}")
        return result

    def _raise_for_wechat_error(self, payload: dict[str, Any]) -> None:
        errcode = payload.get("errcode")
        if errcode not in (None, 0):
            errmsg = payload.get("errmsg", "unknown wechat error")
            logger.error(f"微信接口错误 {errcode}: {errmsg}")
            raise WeChatError(f"微信接口错误 {errcode}: {errmsg}", payload)


wechat_client = WeChatClient()
