from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ============ 通用 Schema ============

class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量，最大 100")
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    
    @classmethod
    def create(cls, items: list[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class SuccessResponse(BaseModel):
    """通用成功响应"""
    ok: bool = True
    message: str = "操作成功"


class ErrorResponse(BaseModel):
    """通用错误响应"""
    ok: bool = False
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# ============ Article Schema ============

class ArticleCreateFromMarkdown(BaseModel):
    title: str | None = None
    markdown: str = Field(..., min_length=1, max_length=500000, description="Markdown 内容")
    instruction: str | None = Field(default=None, max_length=2000, description="AI 润色指令")


class ArticleCreateFromTopic(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="文章主题")
    audience: str | None = Field(default=None, max_length=200, description="目标受众")
    style: str | None = Field(default=None, max_length=200, description="写作风格")
    word_count: int | None = Field(default=1200, ge=100, le=5000, description="目标字数")


class ArticleGenerateRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000, description="重新生成指令")


class AiArticleResult(BaseModel):
    title: str
    digest: str | None = None
    html: str
    cover_prompt: str | None = None
    tags: list[str] = Field(default_factory=list)


class ArticleOut(BaseModel):
    id: int
    title: str
    source_type: str
    source_markdown: str | None = None
    topic_prompt: str | None = None
    current_html: str | None = None
    digest: str | None = None
    cover_prompt: str | None = None
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RevisionOut(BaseModel):
    id: int
    article_id: int
    kind: str
    instruction: str | None = None
    title: str
    digest: str | None = None
    html: str
    ai_payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PublishJobOut(BaseModel):
    id: int
    article_id: int
    target: str
    action: str
    status: str
    draft_media_id: str | None = None
    publish_id: str | None = None
    response_payload: dict[str, Any]
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetOut(BaseModel):
    id: int
    article_id: int | None = None
    source_url: str
    local_path: str | None = None
    wechat_url: str | None = None
    media_id: str | None = None
    asset_type: str
    status: str
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreflightOut(BaseModel):
    ok: bool
    checks: dict[str, bool]
    message: str


class PublicSettingsOut(BaseModel):
    default_author: str = ""
    wechat_account_name: str = ""
    wechat_original_id: str = ""


class PublishRequest(BaseModel):
    action: Literal["create_draft", "publish"] = "create_draft"


class PublishPipelineRequest(BaseModel):
    """一键发布请求"""
    thumb_media_id: str | None = None  # 如果已有封面素材 ID，直接使用


class PublishPipelineOut(BaseModel):
    """一键发布响应"""
    cover_asset: AssetOut | None = None
    draft_job: PublishJobOut | None = None
    publish_job: PublishJobOut | None = None
    error: str | None = None
    stage: str  # init, upload_cover, create_draft, publish, completed
