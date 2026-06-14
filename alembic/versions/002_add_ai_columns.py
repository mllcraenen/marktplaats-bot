"""add ai_score and ai_flags to results

Revision ID: 002
Revises: 001
Create Date: 2026-06-08 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("results", sa.Column("ai_score", sa.Integer(), nullable=True))
    op.add_column("results", sa.Column("ai_flags", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "ai_flags")
    op.drop_column("results", "ai_score")
