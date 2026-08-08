"""Give investigation results a noun to attach to.

Two tables: the incident and its timeline.

The load-bearing index is ``ix_incidents_live_correlation``, and it is partial.
Correlation asks "is there already a live incident for this cause" once per
finding per tick, and a total index would make that a lookup over every incident
the deployment has ever had. Restricted to the open ones it is a lookup over a
handful of rows in a healthy deployment, and it stays a handful however much
history accumulates — which is the difference between correlation costing
nothing and correlation being the reason ticks get slower over a year.

Subjects are JSONB and runs and actions are arrays rather than child tables.
They are read only with their incident and never queried across incidents, so
normalising them would be three joins to render one screen and no query would
ever use it. The one field that *is* queried across incidents has the index
above.

``ix_incidents_age`` is on ``closed_at`` alone and not tenant-scoped, because
retention sweeps the whole deployment at once — the same reasoning the estate's
history indexes carry.

Revision: 0007_incidents
Parent: 0006_signals
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_incidents"
down_revision = "0006_signals"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``IncidentState``, ``IncidentOrigin`` and
#: ``TimelineKind``, with room for one nobody has thought of yet.
_STATE_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "incidents",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("incident_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("correlation_key", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("title", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("origin_id", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("severity", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("state", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("subjects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("run_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("actions", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("close_reason", sa.Text(), nullable=False),
        sa.Column("self_resolved", sa.Boolean(), nullable=False),
        sa.Column("suppressed_by", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "incident_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    # Partial: correlation only ever asks about the live incidents, and a total
    # index would grow with every incident the deployment has ever closed.
    op.create_index(
        "ix_incidents_live_correlation",
        "incidents",
        ["org_id", "correlation_key"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index("ix_incidents_opened", "incidents", ["org_id", "opened_at"])
    op.create_index("ix_incidents_state", "incidents", ["org_id", "state"])
    op.create_index("ix_incidents_team", "incidents", ["org_id", "team_node_id"])
    op.create_index("ix_incidents_age", "incidents", ["closed_at"])

    op.create_table(
        "incident_timeline",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("entry_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("incident_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("kind", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "entry_id"),
        sa.ForeignKeyConstraint(
            ["org_id", "incident_id"],
            ["incidents.org_id", "incidents.incident_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_incident_timeline_incident",
        "incident_timeline",
        ["org_id", "incident_id", "at"],
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("incident_timeline")
    op.drop_table("incidents")
