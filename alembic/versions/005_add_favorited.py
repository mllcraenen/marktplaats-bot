"""add favorited column to results

Revision ID: 005
Revises: 004
Create Date: 2026-06-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("results", sa.Column("favorited", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("results", "favorited")
