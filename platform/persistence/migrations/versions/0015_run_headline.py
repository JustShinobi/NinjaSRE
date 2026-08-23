"""Give a run a headline: one sentence, apart from the document it wrote.

Before this, ``agent_runs.summary`` carried the whole document — what the
model wrote in full — and nothing carried a shorter sentence a title, a list
column, or a push notification could use without cutting the document down
to size. Cutting the document is exactly the defect this migration exists to
stop: a heading grabbed from the top of a markdown report is not a title,
it is a truncation wearing one.

``NOT NULL DEFAULT ''``, like every free-text column this series has added.
Every run that predates this migration keeps the document it always had in
``summary``; its headline is derived at read time from the run's own subject
— never backfilled here, because writing a synthesised sentence into the run
row would record something the read path inferred as though it were a fact
the run itself produced.

Revision: 0015_run_headline
Parent: 0014_timeline_evidence
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_run_headline"
down_revision = "0014_timeline_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "agent_runs",
        sa.Column("headline", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_column("agent_runs", "headline")
