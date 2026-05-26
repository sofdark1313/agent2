"""
统一的异常层次结构
"""
from typing import Any


class AppError(Exception):
    """应用基础异常"""
    
    def __init__(self, message: str, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or "APP_ERROR"
        self.details = details or {}


class ValidationError(AppError):
    """验证错误"""
    
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", details={"field": field} if field else {})
        self.field = field


class NotFoundError(AppError):
    """资源不存在"""
    
    def __init__(self, resource: str, resource_id: int | str | None = None) -> None:
        message = f"{resource} not found"
        if resource_id is not None:
            message = f"{resource} with id {resource_id} not found"
        super().__init__(message, code="NOT_FOUND", details={"resource": resource, "id": resource_id})


class ConflictError(AppError):
    """状态冲突"""
    
    def __init__(self, message: str, current_state: str | None = None) -> None:
        super().__init__(message, code="CONFLICT", details={"current_state": current_state} if current_state else {})


class ExternalServiceError(AppError):
    """外部服务错误基类"""
    
    def __init__(self, service: str, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message, code=f"{service.upper()}_ERROR", details={"payload": payload or {}})
        self.service = service
        self.payload = payload or {}


class WeChatError(ExternalServiceError):
    """微信 API 错误"""
    
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__("wechat", message, payload)


class AiProviderError(ExternalServiceError):
    """AI 服务错误"""
    
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__("ai", message, payload)


class PublishingError(ConflictError):
    """发布流程错误"""
    pass


class FileValidationError(ValidationError):
    """文件验证错误"""
    
    def __init__(self, message: str, filename: str | None = None) -> None:
        super().__init__(message, field="file")
        self.filename = filename
