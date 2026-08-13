"""Give the deployment somewhere to remember what it has actually checked.

One table, and it is deliberately the shape of current state rather than of a
log. The primary key is ``(org_id, kind, subject)``, so checking the same thing
twice updates one row and there is exactly one answer per thing without any
writer having to delete the previous one.

No age index and no retention class, for the same reason ``transit_samples`` has
none: the table is bounded by how many things a deployment can check, and ageing
it would delete "does this work" from precisely the integrations nobody has
touched in a while — which is the question the row exists to answer.

``kind`` is in the key because a vendor integration and a model provider can
share a name, and one row for both would put a verdict about one onto the other.

Revision: 0011_verifications
Parent: 0010_transit
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_verifications"
down_revision = "0010_transit"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
#: Repeated rather than imported, for the reason 0005 gives: a migration
#: describes the database it created.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``VerificationOutcome`` and
#: ``VerificationSubject``, with room for one nobody has thought of yet.
_ENUM_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "verifications",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("kind", sa.String(length=_ENUM_LENGTH), nullable=False),
        sa.Column("subject", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("outcome", sa.String(length=_ENUM_LENGTH), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("checked_by", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("model_id", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "kind", "subject"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("verifications")
