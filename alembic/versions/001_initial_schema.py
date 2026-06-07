"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-07 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_text", sa.String(500), nullable=False),
        sa.Column("nl_keywords", sa.String(500), nullable=True),
        sa.Column("en_keywords", sa.String(500), nullable=True),
        sa.Column("max_budget", sa.Float(), nullable=True),
        sa.Column("radius_km", sa.Integer(), nullable=False),
        sa.Column("postcode", sa.String(10), nullable=False),
        sa.Column("max_age_years", sa.Integer(), nullable=True),
        sa.Column("required_specs", sa.Text(), nullable=True),
        sa.Column("required_brands", sa.Text(), nullable=True),
        sa.Column("excluded_brands", sa.Text(), nullable=True),
        sa.Column("exclude_business", sa.Boolean(), nullable=False),
        sa.Column("relevance_threshold", sa.Integer(), nullable=False),
        sa.Column("ranking_mode", sa.String(50), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), sa.ForeignKey("searches.id"), nullable=False),
        sa.Column("listing_id", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("photo_count", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("seller_type", sa.String(20), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("deal_score", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.Column("seen", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
    )
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), sa.ForeignKey("searches.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parsed_changes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
    )


def downgrade() -> None:
    op.drop_table("feedbacks")
    op.drop_table("results")
    op.drop_table("searches")
