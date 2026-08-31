"""Give a run its subject: what it was asked to investigate.

Before this, the objective typed into ``POST /v1/investigations`` — or
derived from an alert's incident — reached the runtime and nothing else. The
row in ``agent_runs`` never carried it, so the only sentence a live run could
be named by was invented at read time from ``trigger`` and ``alert_id``:
"interactive investigation", or a hash. This column is where the real
subject starts being a fact the run itself carries, from the moment it
starts rather than from the moment it finishes.

``NOT NULL DEFAULT ''``, the same convention ``0015_run_headline`` set for a
free-text column on this table. A run that predates this migration keeps
reading as having declared no subject — the read path synthesises a generic
headline for that case rather than this migration inventing one by writing a
value nobody's row actually recorded.

Revision: 0020_run_objective
Parent: 0019_users_email_optional
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_run_objective"
down_revision = "0019_users_email_optional"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "agent_runs",
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_column("agent_runs", "objective")
