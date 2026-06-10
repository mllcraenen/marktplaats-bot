"""add applied / applied_at columns to feedbacks

Revision ID: 006
Revises: 005
Create Date: 2026-06-10 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feedbacks", sa.Column("applied", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("feedbacks", sa.Column("applied_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("feedbacks", "applied_at")
    op.drop_column("feedbacks", "applied")
