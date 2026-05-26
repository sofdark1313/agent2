"""add indexes for common queries

Revision ID: 0002_add_indexes
Revises: 0001_initial
Create Date: 2026-05-25 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_add_indexes"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # articles 表索引
    op.create_index("ix_articles_status", "articles", ["status"])
    op.create_index("ix_articles_created_at", "articles", ["created_at"])
    
    # publish_jobs 表索引
    op.create_index("ix_publish_jobs_status", "publish_jobs", ["status"])
    op.create_index("ix_publish_jobs_article_id", "publish_jobs", ["article_id"])
    op.create_index("ix_publish_jobs_article_action", "publish_jobs", ["article_id", "action"])
    
    # assets 表索引
    op.create_index("ix_assets_article_id", "assets", ["article_id"])
    op.create_index(
        "ix_assets_article_type_status",
        "assets",
        ["article_id", "asset_type", "status"],
    )
    
    # revisions 表索引
    op.create_index("ix_revisions_article_id", "revisions", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_revisions_article_id", "revisions")
    op.drop_index("ix_assets_article_type_status", "assets")
    op.drop_index("ix_assets_article_id", "assets")
    op.drop_index("ix_publish_jobs_article_action", "publish_jobs")
    op.drop_index("ix_publish_jobs_article_id", "publish_jobs")
    op.drop_index("ix_publish_jobs_status", "publish_jobs")
    op.drop_index("ix_articles_created_at", "articles")
    op.drop_index("ix_articles_status", "articles")
