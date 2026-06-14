"""add image_urls, is_bidding, ai_reason, query_enhanced, last_analyzed_at

Revision ID: 003
Revises: 002
Create Date: 2026-06-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deduplicate results: keep earliest row per (search_id, listing_id)
    op.execute("""
        DELETE FROM results
        WHERE id NOT IN (
            SELECT MIN(id) FROM results GROUP BY search_id, listing_id
        )
    """)

    op.add_column("results", sa.Column("ai_reason", sa.Text(), nullable=True))
    op.add_column("results", sa.Column("image_urls", sa.Text(), nullable=True))
    op.add_column("results", sa.Column("is_bidding", sa.Boolean(), nullable=False, server_default="0"))

    op.add_column("searches", sa.Column("query_enhanced", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("searches", sa.Column("last_analyzed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "is_bidding")
    op.drop_column("results", "image_urls")
    op.drop_column("results", "ai_reason")
    op.drop_column("searches", "last_analyzed_at")
    op.drop_column("searches", "query_enhanced")
