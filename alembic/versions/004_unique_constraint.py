"""add unique constraint on (search_id, listing_id) to prevent duplicate results

Revision ID: 004
Revises: 003
Create Date: 2026-06-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deduplicate any remaining duplicates (safety net — 003 should have cleared them)
    op.execute("""
        DELETE FROM results
        WHERE id NOT IN (
            SELECT MIN(id) FROM results GROUP BY search_id, listing_id
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_results_search_listing "
        "ON results(search_id, listing_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_results_search_listing")
