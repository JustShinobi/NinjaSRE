"""Give a timeline entry somewhere to carry the query an evidence step ran.

Before this, ``incident_timeline`` could only say a conclusion happened
(``cause``) and add one loose sentence about it (``detail``). An evidence
entry needs more than a sentence: the query that was actually run and the
result it actually returned, so a screen can draw what was asked and what
came back rather than only what somebody concluded from it. A conclusion
that cannot point at the query and result behind it is a hypothesis, not a
diagnosis.

Two columns rather than one JSON blob, matching ``cause``/``detail``'s own
shape on this table: each is its own column because each is read and
rendered on its own, in its own block, and a screen that wanted only the
query would otherwise have to parse a blob to get it.

``NOT NULL DEFAULT ''``, like every other free-text column on this table.
Every entry that predates this migration is a lifecycle entry — a timeline
never held an evidence step before this feature — so backfilling every
existing row with an empty string is not a guess about a value that once
existed; it is the correct, permanent reading for a kind that never carries
one.

Revision: 0014_timeline_evidence
Parent: 0013_local_password
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_timeline_evidence"
down_revision = "0013_local_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "incident_timeline",
        sa.Column("query", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "incident_timeline",
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_column("incident_timeline", "result")
    op.drop_column("incident_timeline", "query")
