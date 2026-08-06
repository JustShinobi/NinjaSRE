"""Give every run an append-only event log with a cursor a client can hold.

The trace tables record *state* — what the run is, what it thought, what it
called, what it saw. None of them can answer the question a client asks after a
dropped connection: what happened after position N. Answering it from the state
tables would mean reconstructing an ordering across four tables whose timestamps
routinely collide, and getting it wrong means an event delivered twice or not at
all.

So the log is its own table, and ``sequence`` is its own column rather than a
derived ordering. It is assigned per run, inside the writing transaction, which
is what makes the cursor stable across reads and keeps two busy runs from
contending on one counter.

Revision: 0004_trace_events
Parent: 0003_identity_audit
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_trace_events"
down_revision = "0003_identity_audit"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
#: Repeated rather than imported, because a migration describes the database it
#: created and a model that changes later must not change what this did.
_ID_LENGTH = 128
_NAME_LENGTH = 256


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "trace_events",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("event_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("run_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("turn_id", sa.String(length=_ID_LENGTH), nullable=True),
        sa.Column("kind", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "event_id"),
        # Composite and cascading, like every other child of a run: an event
        # cannot reference a run in another organisation, and deleting a run
        # takes its log with it.
        sa.ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["agent_runs.org_id", "agent_runs.run_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trace_events_cursor",
        "trace_events",
        ["org_id", "run_id", "sequence"],
        unique=False,
    )
    op.create_index("ix_trace_events_kind", "trace_events", ["org_id", "kind"], unique=False)


def downgrade() -> None:
    """Undo the change."""
    op.drop_index("ix_trace_events_kind", table_name="trace_events")
    op.drop_index("ix_trace_events_cursor", table_name="trace_events")
    op.drop_table("trace_events")
