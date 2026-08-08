"""Give the deployment a noun for the things it is responsible for.

Four tables. The inventory itself, the log of every health transition, the links
from a resource back to what touched it, and the record of each discovery sweep.

The one shape worth explaining is what is *not* here: ``parent_id`` carries no
foreign key. A sweep enumerates a provider's inventory in whatever order the
provider returns it, so a guest routinely arrives before the node it runs on;
and a source that names a parent it does not itself enumerate — a guest whose
node comes from a different integration — has a parent that will never exist as
a row from this source's point of view. A foreign key would make both cases
unwritable, so the relationship is an indexed column here and an edge in the
knowledge graph, which is where "what does this affect" is answered anyway.

``(org_id, source, native_id)`` is unique **among present resources**, and that
partial constraint is the whole of the no-duplicates guarantee. The identity
derivation that produces ``resource_id`` lives above the storage layer, so
without this the property would hold only for as long as every caller went
through it. It is partial rather than total because a provider that reuses an
identifier after a deletion is describing a different thing: the retired
resource keeps its row and its history, and the newcomer gets its own.

Revision: 0005_estate
Parent: 0004_trace_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_estate"
down_revision = "0004_trace_events"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
#: Repeated rather than imported, because a migration describes the database it
#: created and a model that changes later must not change what this did.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``ResourceHealth`` and ``SweepOutcome`` with
#: room for one nobody has thought of yet, narrow enough to stay out of TOAST.
_STATE_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "estate_resources",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("kind", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("source", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("native_id", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("display_name", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("correlation_key", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("parent_id", sa.String(length=_ID_LENGTH), nullable=True),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("labels", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("health", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("derivation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("absent_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maintenance_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maintenance_reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "resource_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    # Partial rather than a plain unique constraint: only one *present* resource
    # per source and native identifier. A provider that reuses an identifier
    # after a deletion gets a new row beside the absent one, which is what keeps
    # the retired resource's history from being inherited by its successor.
    op.create_index(
        "uq_estate_resources_native",
        "estate_resources",
        ["org_id", "source", "native_id"],
        unique=True,
        postgresql_where=sa.text("absent_since IS NULL"),
    )
    op.create_index(
        "ix_estate_resources_correlation",
        "estate_resources",
        ["org_id", "kind", "correlation_key"],
    )
    op.create_index("ix_estate_resources_kind", "estate_resources", ["org_id", "kind"])
    op.create_index("ix_estate_resources_health", "estate_resources", ["org_id", "health"])
    op.create_index("ix_estate_resources_parent", "estate_resources", ["org_id", "parent_id"])
    op.create_index("ix_estate_resources_team", "estate_resources", ["org_id", "team_node_id"])
    op.create_index("ix_estate_resources_source", "estate_resources", ["org_id", "source"])

    op.create_table(
        "estate_health_transitions",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("transition_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("state", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("previous_state", sa.String(length=_STATE_LENGTH), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("signal", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("org_id", "transition_id"),
        sa.ForeignKeyConstraint(
            ["org_id", "resource_id"],
            ["estate_resources.org_id", "estate_resources.resource_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_estate_transitions_resource",
        "estate_health_transitions",
        ["org_id", "resource_id", "occurred_at"],
    )
    # Retention sweeps across every tenant at once, so its index is on the
    # timestamp alone. Leading with ``org_id`` would make the sweep a scan.
    op.create_index("ix_estate_transitions_age", "estate_health_transitions", ["occurred_at"])

    op.create_table(
        "estate_resource_references",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("reference_kind", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("reference_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "resource_id", "reference_kind", "reference_id"),
        sa.ForeignKeyConstraint(
            ["org_id", "resource_id"],
            ["estate_resources.org_id", "estate_resources.resource_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_estate_references_resource",
        "estate_resource_references",
        ["org_id", "resource_id", "recorded_at"],
    )
    op.create_index("ix_estate_references_age", "estate_resource_references", ["recorded_at"])

    op.create_table(
        "estate_discovery_sweeps",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("sweep_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("source", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=_STATE_LENGTH), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "sweep_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_estate_sweeps_source",
        "estate_discovery_sweeps",
        ["org_id", "source", "started_at"],
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("estate_discovery_sweeps")
    op.drop_table("estate_resource_references")
    op.drop_table("estate_health_transitions")
    op.drop_table("estate_resources")
