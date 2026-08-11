"""Give the deployment somewhere to remember what crossed its boundary.

Two tables, and the difference between them is the whole design.

``transit_deliveries`` is an append-and-age table: one row per crossing, in
either direction, swept under its own retention class. Its primary key is the
caller's derived delivery id so a retried ledger write is one row, and
``ix_transit_age`` is on the timestamp alone — not tenant-scoped — because the
sweep runs across the deployment and a per-tenant index would be scanned once
per organisation.

``transit_samples`` is not aged at all. It is keyed by ``(org_id, source)``, so
there is exactly one masked payload per source by construction rather than by
every writer remembering to delete the previous one, and the table is bounded by
how many sources exist. Ageing it would delete "what does this source send" from
precisely the sources that send rarely, which is the question the sample exists
to answer.

The body column holds text that has already been through the masking policy.
There is no column for a raw payload, so there is none to forget to clear.

Revision: 0010_transit
Parent: 0009_sweep_findings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_transit"
down_revision = "0009_sweep_findings"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
#: Repeated rather than imported, for the reason 0005 gives: a migration
#: describes the database it created.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``TransitDirection``, ``TransitOutcome`` and
#: ``MaskingLevel``, with room for one nobody has thought of yet.
_ENUM_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "transit_deliveries",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("delivery_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("direction", sa.String(length=_ENUM_LENGTH), nullable=False),
        sa.Column("source", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=_ENUM_LENGTH), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("matched_rule", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("run_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("incident_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("event_type", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "delivery_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_transit_recent",
        "transit_deliveries",
        ["org_id", "direction", "source", "occurred_at"],
    )
    op.create_index("ix_transit_age", "transit_deliveries", ["occurred_at"])

    op.create_table(
        "transit_samples",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("source", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("masking_policy", sa.String(length=_ENUM_LENGTH), nullable=False),
        sa.Column("delivery_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "source"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("transit_samples")
    op.drop_table("transit_deliveries")
