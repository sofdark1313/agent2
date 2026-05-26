"""
日志配置模块
"""
import logging
import sys
from typing import Any

from app.core.config import settings


def setup_logging() -> None:
    """配置应用日志"""
    log_level = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    
    # 配置根日志器
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    # 降低第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器"""
    return logging.getLogger(name)


class LoggerMixin:
    """为类提供日志功能的 Mixin"""
    
    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__name__)


def log_api_call(
    logger: logging.Logger,
    service: str,
    operation: str,
    *,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """记录 API 调用日志"""
    extra = {
        "service": service,
        "operation": operation,
    }
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    
    if error:
        logger.error(
            f"{service}.{operation} failed: {error}",
            extra=extra,
        )
    else:
        logger.info(
            f"{service}.{operation} succeeded",
            extra=extra,
        )
