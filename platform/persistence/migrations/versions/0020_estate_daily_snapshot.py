"""Give the estate a memory of what it looked like, one row per day.

Before this, `EstateRepository.summarise` could only ever answer "right now" —
there was nowhere a KPI's sparkline could read a trend from, because nothing
recorded what the estate's counts were yesterday, or the day before.

One table, and the primary key is the natural key: `(org_id, snapshot_date)`.
That is what makes a write an upsert rather than a check-then-insert — the
sweeper that writes this table calls `ON CONFLICT DO NOTHING`, so the first
sweep of a day to reach it is the one whose counts stand for that day, and
every later sweep the same day is a confirmation rather than a correction.

Revision: 0020_estate_daily_snapshot
Parent: 0019_users_email_optional
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_estate_daily_snapshot"
down_revision = "0019_users_email_optional"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` on the day this ran. Repeated rather than
#: imported, for the reason 0005 gives: a migration describes the database it
#: created.
_ID_LENGTH = 128


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "estate_daily",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "counts_by_kind", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "counts_by_health", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "snapshot_date"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("estate_daily")
