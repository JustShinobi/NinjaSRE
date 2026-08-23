"""Index ``incidents.run_ids`` for containment, so a run's incident is a lookup.

Before this, "which incident does this run belong to" had no index to answer
from: the array lived on the row with nothing indexing its contents, so
finding it meant scanning incidents or, as the console did, paging through
``/v1/incidents`` hoping the right one was on an early page. A GIN index over
the array is what turns ``run_ids @> ARRAY[:run_id]`` into an index scan
instead of a sequential one — the same reasoning already applied to
``episodes.components`` for the same kind of question.

No column changes, so nothing to backfill and nothing to reverse but the
index itself.

Revision: 0016_incident_run_ids_index
Parent: 0015_run_headline
"""

from __future__ import annotations

from alembic import op

revision = "0016_incident_run_ids_index"
down_revision = "0015_run_headline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.create_index(
        "ix_incidents_run_ids",
        "incidents",
        ["run_ids"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_index("ix_incidents_run_ids", table_name="incidents")
