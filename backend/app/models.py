from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

LongText = Text().with_variant(LONGTEXT(), "mysql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_markdown: Mapped[str | None] = mapped_column(LongText)
    topic_prompt: Mapped[str | None] = mapped_column(LongText)
    current_html: Mapped[str | None] = mapped_column(LongText)
    digest: Mapped[str | None] = mapped_column(String(255))
    cover_prompt: Mapped[str | None] = mapped_column(LongText)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    revisions: Mapped[list["Revision"]] = relationship(back_populates="article")
    assets: Mapped[list["Asset"]] = relationship(back_populates="article")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="article")


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction: Mapped[str | None] = mapped_column(LongText)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    digest: Mapped[str | None] = mapped_column(String(255))
    html: Mapped[str] = mapped_column(LongText, nullable=False)
    ai_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped[Article] = relationship(back_populates="revisions")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"))
    source_url: Mapped[str] = mapped_column(LongText, nullable=False)
    local_path: Mapped[str | None] = mapped_column(LongText)
    wechat_url: Mapped[str | None] = mapped_column(LongText)
    media_id: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(LongText)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped[Article | None] = relationship(back_populates="assets")


class PublishJob(Base, TimestampMixin):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    target: Mapped[str] = mapped_column(String(32), default="wechat", nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    draft_media_id: Mapped[str | None] = mapped_column(String(255))
    publish_id: Mapped[str | None] = mapped_column(String(255))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(LongText)

    article: Mapped[Article] = relationship(back_populates="publish_jobs")


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(LongText)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
