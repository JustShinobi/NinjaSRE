"""Add the synthesised strategy table.

One table, and its primary key is the synthesis key itself — the team, the issue
type, and the normalised component — rather than a generated id. There is one
playbook per key by definition, so the upsert that persists a generation is a
primary-key upsert and two concurrent syntheses converge on one row whatever
order they commit in.

The index is on ``(org_id, team_node_id, generated_at)``: the two questions asked
of this table are "what is the playbook for this key", which the primary key
answers, and "what playbooks does this team hold, newest first", which is the
console's listing and is what the index is for.

Revision: 0002_strategies
Parent: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_strategies"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "strategies",
        sa.Column("org_id", sa.String(length=128), nullable=False),
        sa.Column("team_node_id", sa.String(length=128), nullable=False),
        sa.Column("issue_type", sa.String(length=256), nullable=False),
        sa.Column("component_key", sa.String(length=256), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id", "team_node_id", "issue_type", "component_key"),
    )
    op.create_index(
        "ix_strategies_generated",
        "strategies",
        ["org_id", "team_node_id", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_index("ix_strategies_generated", table_name="strategies")
    op.drop_table("strategies")
