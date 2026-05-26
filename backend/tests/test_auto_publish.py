"""自动发布 pipeline 与状态轮询的测试。

不依赖真实 MySQL —— 测试用 SQLite in-memory 重新挂 Base.metadata,
用 monkeypatch 把 wechat_client 的方法替换成 AsyncMock。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Text

import app.models as models
from app.db.base import Base
from app.models import Article, Asset, PublishJob

# SQLite 不支持 LONGTEXT,把 LongText 替换成 Text 让 metadata.create_all 通过
models.LongText = Text()


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # 把模型里所有 LONGTEXT 列在 SQLite 上当 Text 用
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, LONGTEXT):
                column.type = Text()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _create_article(db, status: str = "generated", html: str = "<p>hello</p>") -> Article:
    article = Article(
        title="测试文章",
        source_type="topic",
        current_html=html,
        digest="摘要",
        cover_prompt=None,
        tags=[],
        status=status,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def test_publish_pipeline_happy_path(db_session, monkeypatch):
    """从已有 thumb_media_id 走完整 pipeline,直到 publishing 状态。"""
    from app.services import assets as assets_module
    from app.services import publishing as publishing_module
    from app.services import wechat as wechat_module

    monkeypatch.setattr(wechat_module.wechat_client, "get_access_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(wechat_module.wechat_client, "create_draft", AsyncMock(return_value={"media_id": "DRAFT_MEDIA_ID"}))
    monkeypatch.setattr(wechat_module.wechat_client, "publish", AsyncMock(return_value={"publish_id": "PUB_ID_1"}))
    # pipeline 不应该尝试上传正文图(html 没有 img),也不应该再上传封面
    monkeypatch.setattr(wechat_module.wechat_client, "upload_article_image", AsyncMock(side_effect=AssertionError("不应该上传图片")))
    monkeypatch.setattr(wechat_module.wechat_client, "upload_cover_material", AsyncMock(side_effect=AssertionError("不应该上传封面")))

    monkeypatch.setattr(publishing_module.settings, "wechat_auto_publish", True)

    article = _create_article(db_session)

    result = asyncio.run(
        publishing_module.publish_pipeline(
            db_session, article, cover_path=None, thumb_media_id="THUMB_MEDIA_ID"
        )
    )

    assert result["error"] is None, result
    assert result["stage"] == "completed"
    assert result["draft_job"].status == "succeeded"
    assert result["draft_job"].draft_media_id == "DRAFT_MEDIA_ID"
    assert result["publish_job"].status == "publishing"
    assert result["publish_job"].publish_id == "PUB_ID_1"
    db_session.refresh(article)
    assert article.status == "publishing"


def test_publish_pipeline_blocks_when_auto_publish_disabled(db_session, monkeypatch):
    """WECHAT_AUTO_PUBLISH=false 时只到 draft_created,不调 submit。"""
    from app.services import publishing as publishing_module
    from app.services import wechat as wechat_module

    submit_mock = AsyncMock(side_effect=AssertionError("不应该提交发布"))
    monkeypatch.setattr(wechat_module.wechat_client, "get_access_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(wechat_module.wechat_client, "create_draft", AsyncMock(return_value={"media_id": "DRAFT"}))
    monkeypatch.setattr(wechat_module.wechat_client, "publish", submit_mock)
    monkeypatch.setattr(publishing_module.settings, "wechat_auto_publish", False)

    article = _create_article(db_session)
    result = asyncio.run(
        publishing_module.publish_pipeline(db_session, article, cover_path=None, thumb_media_id="THUMB")
    )

    # publish_wechat_article 在 auto_publish=False 时把 publish job 标 failed
    assert result["draft_job"].status == "succeeded"
    assert result["publish_job"].status == "failed"
    assert "WECHAT_AUTO_PUBLISH" in (result["publish_job"].error or "")
    submit_mock.assert_not_awaited()


def test_publish_pipeline_blocked_for_generating_article(db_session):
    """文章在 generating 状态时,pipeline 必须拒绝。"""
    from app.core.exceptions import PublishingError
    from app.services import publishing as publishing_module

    article = _create_article(db_session, status="generating")
    with pytest.raises(PublishingError):
        asyncio.run(
            publishing_module.publish_pipeline(
                db_session, article, cover_path=None, thumb_media_id="THUMB"
            )
        )


def test_publish_idempotency_returns_existing_job(db_session, monkeypatch):
    """同一 draft_media_id 二次提交,应该复用已有 PublishJob,不重复调微信。"""
    from app.services import publishing as publishing_module
    from app.services import wechat as wechat_module

    publish_mock = AsyncMock(return_value={"publish_id": "PUB_ID"})
    monkeypatch.setattr(wechat_module.wechat_client, "get_access_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(wechat_module.wechat_client, "publish", publish_mock)
    monkeypatch.setattr(publishing_module.settings, "wechat_auto_publish", True)

    article = _create_article(db_session)
    first = asyncio.run(publishing_module.publish_wechat_article(db_session, article, "DRAFT_X"))
    second = asyncio.run(publishing_module.publish_wechat_article(db_session, article, "DRAFT_X"))

    assert first.id == second.id
    assert publish_mock.await_count == 1


def test_poll_publish_status_marks_published(db_session, monkeypatch):
    """publish_status=0 -> 文章 published,job succeeded。"""
    from app.services import publishing as publishing_module
    from app.services import wechat as wechat_module

    monkeypatch.setattr(
        wechat_module.wechat_client,
        "get_publish_status",
        AsyncMock(return_value={"publish_status": 0, "article_detail": {"item": []}}),
    )

    article = _create_article(db_session, status="publishing")
    job = PublishJob(
        article_id=article.id,
        target="wechat",
        action="publish",
        status="publishing",
        publish_id="PUB_ID",
        request_payload={},
        response_payload={},
    )
    db_session.add(job)
    db_session.commit()

    asyncio.run(publishing_module.poll_publish_status(db_session, job))

    db_session.refresh(article)
    db_session.refresh(job)
    assert article.status == "published"
    assert job.status == "succeeded"


def test_poll_publish_status_marks_failed(db_session, monkeypatch):
    """publish_status=4 (审核不通过) -> 文章 publish_failed,job failed。"""
    from app.services import publishing as publishing_module
    from app.services import wechat as wechat_module

    monkeypatch.setattr(
        wechat_module.wechat_client,
        "get_publish_status",
        AsyncMock(return_value={"publish_status": 4, "fail_idx": [1]}),
    )

    article = _create_article(db_session, status="publishing")
    job = PublishJob(
        article_id=article.id,
        target="wechat",
        action="publish",
        status="publishing",
        publish_id="PUB_ID",
        request_payload={},
        response_payload={},
    )
    db_session.add(job)
    db_session.commit()

    asyncio.run(publishing_module.poll_publish_status(db_session, job))

    db_session.refresh(article)
    db_session.refresh(job)
    assert article.status == "publish_failed"
    assert job.status == "failed"
    assert "审核" in (job.error or "")


def test_upload_body_images_idempotent_reuse(db_session, monkeypatch):
    """同一 source_url 第二次调用应该复用 Asset,不再重复上传。"""
    from app.services import assets as assets_module
    from app.services import wechat as wechat_module

    upload_mock = AsyncMock(return_value="https://mmbiz.qpic.cn/x.jpg")
    monkeypatch.setattr(wechat_module.wechat_client, "upload_article_image", upload_mock)
    monkeypatch.setattr(wechat_module.wechat_client, "get_access_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        assets_module,
        "_materialize_image",
        AsyncMock(return_value="/tmp/x.jpg"),
    )

    article = _create_article(
        db_session, html='<p><img src="https://example.com/a.png"></p>'
    )

    # 第一轮:正常上传
    asyncio.run(assets_module.upload_body_images(db_session, article))
    assert upload_mock.await_count == 1

    # 第二轮:同一文章,同一图,应该复用
    asyncio.run(assets_module.upload_body_images(db_session, article))
    assert upload_mock.await_count == 1, "第二次不应该重复上传"

    # 数据库里只保留 1 个 uploaded 状态的 body_image
    uploaded = (
        db_session.query(Asset)
        .filter(
            Asset.article_id == article.id,
            Asset.asset_type == "body_image",
            Asset.status == "uploaded",
        )
        .all()
    )
    assert len(uploaded) == 1
