from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ArticleCreateFromMarkdown(BaseModel):
    title: str | None = None
    markdown: str
    instruction: str | None = None


class ArticleCreateFromTopic(BaseModel):
    topic: str
    audience: str | None = None
    style: str | None = None
    word_count: int | None = Field(default=1200, ge=300, le=5000)


class ArticleGenerateRequest(BaseModel):
    instruction: str


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


class PublishRequest(BaseModel):
    action: Literal["create_draft", "publish"] = "create_draft"
