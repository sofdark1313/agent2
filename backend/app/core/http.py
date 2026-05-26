"""
HTTP 客户端工具，带重试机制
"""
import asyncio
import time
from typing import Any, Callable, TypeVar

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def retry_async(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int | None = None,
    delay: float | None = None,
    exceptions: tuple[type[Exception], ...] = (httpx.HTTPError, httpx.TimeoutException),
    **kwargs: Any,
) -> T:
    """
    异步重试装饰器
    
    Args:
        func: 要重试的异步函数
        max_attempts: 最大重试次数
        delay: 重试间隔（秒）
        exceptions: 需要重试的异常类型
    
    Returns:
        函数返回值
    
    Raises:
        最后一次尝试的异常
    """
    max_attempts = max_attempts or settings.http_retry_attempts
    delay = delay or settings.http_retry_delay
    
    last_exception: Exception | None = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as exc:
            last_exception = exc
            if attempt < max_attempts:
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed: {exc}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay * attempt)  # 指数退避
            else:
                logger.error(f"All {max_attempts} attempts failed: {exc}")
    
    raise last_exception  # type: ignore


def retry_sync(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int | None = None,
    delay: float | None = None,
    exceptions: tuple[type[Exception], ...] = (httpx.HTTPError, httpx.TimeoutException),
    **kwargs: Any,
) -> T:
    """
    同步重试装饰器
    """
    max_attempts = max_attempts or settings.http_retry_attempts
    delay = delay or settings.http_retry_delay
    
    last_exception: Exception | None = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as exc:
            last_exception = exc
            if attempt < max_attempts:
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed: {exc}. Retrying in {delay}s..."
                )
                time.sleep(delay * attempt)
            else:
                logger.error(f"All {max_attempts} attempts failed: {exc}")
    
    raise last_exception  # type: ignore


class RetryClient:
    """带重试功能的 HTTP 客户端"""
    
    def __init__(
        self,
        timeout: int = 30,
        max_attempts: int | None = None,
        retry_delay: float | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_attempts = max_attempts or settings.http_retry_attempts
        self.retry_delay = retry_delay or settings.http_retry_delay
    
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET 请求，带重试"""
        return await retry_async(
            self._do_get,
            url,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            **kwargs,
        )
    
    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST 请求，带重试"""
        return await retry_async(
            self._do_post,
            url,
            max_attempts=self.max_attempts,
            delay=self.retry_delay,
            **kwargs,
        )
    
    async def _do_get(self, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response
    
    async def _do_post(self, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, **kwargs)
            # 不自动 raise_for_status，让调用方处理业务错误
            return response
