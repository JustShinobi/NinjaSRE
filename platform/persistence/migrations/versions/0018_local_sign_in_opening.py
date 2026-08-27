"""Record the one fact that decides whether a deployment's local sign-in exists.

Before this, the door a local sign-in walks through was a single field being
set on the running process — the environment-configured account. That is
enough for a deployment that configures one at start-up, and it has no answer
for a deployment that wants to open the door later, by running a command,
without restarting anything: a field read once at construction cannot become
true while the process is already up.

This table is that second, later answer. One row per organisation, written
once by whichever caller — the administrator command or the bootstrap
exchange — gets there first, and never rewritten afterwards: the primary key
is ``org_id`` alone, so a second attempt collides on the primary key rather
than on a rule invented for the purpose.

Revision: 0018_local_sign_in_opening
Parent: 0017_incident_public_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_local_sign_in_opening"
down_revision = "0017_incident_public_id"
branch_labels = None
depends_on = None

_OPENED_VIA_LENGTH = 64


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "local_sign_in_openings",
        sa.Column("org_id", sa.String(length=128), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_via", sa.String(length=_OPENED_VIA_LENGTH), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    """Undo the change.

    Drops the table and nothing else. No user, grant, or password this table
    never held is touched — a deployment reverted past this revision simply
    stops being able to tell, from the database alone, whether its local
    sign-in has ever opened; the accounts it already created keep working.
    """
    op.drop_table("local_sign_in_openings")
