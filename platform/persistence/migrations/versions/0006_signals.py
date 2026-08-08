"""Give the deployment somewhere to remember what it has been watching.

One table, and the two indexes that decide whether it stays affordable.

``ix_signals_window`` leads with ``(org_id, name, resource_id, observed_at)``
because that is the shape of every read a detector makes: one signal, about one
resource, over one window. Ordering the last component by time is also what
makes ``DISTINCT ON`` for "the newest sample per resource" a backwards walk over
the index rather than a sort of the table.

``ix_signals_age`` is on the timestamp alone and deliberately not tenant-scoped.
Retention sweeps across the whole deployment at once; leading with ``org_id``
would make the sweep one index scan per organisation, which is the cost that
turns a bounded table into an unbounded one.

The primary key is the derived signal id, so an append is an upsert and a
retried poll cannot double a sample. That is a storage-level guarantee on
purpose: the derivation lives above this layer, and a property enforced only by
every caller remembering to use it is not a property.

Revision: 0006_signals
Parent: 0005_estate
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_signals"
down_revision = "0005_estate"
branch_labels = None
depends_on = None

#: Matches ``models.ID_LENGTH`` and ``models.NAME_LENGTH`` on the day this ran.
#: Repeated rather than imported, for the reason 0005 gives: a migration
#: describes the database it created.
_ID_LENGTH = 128
_NAME_LENGTH = 256

#: Wide enough for every member of ``SignalKind`` with room for one nobody has
#: thought of yet.
_KIND_LENGTH = 32


def upgrade() -> None:
    """Apply the change."""
    op.create_table(
        "observation_signals",
        sa.Column("org_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("signal_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("name", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=_ID_LENGTH), nullable=False),
        sa.Column("source", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("kind", sa.String(length=_KIND_LENGTH), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=_NAME_LENGTH), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("org_id", "signal_id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.org_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_signals_window",
        "observation_signals",
        ["org_id", "name", "resource_id", "observed_at"],
    )
    op.create_index("ix_signals_age", "observation_signals", ["observed_at"])


def downgrade() -> None:
    """Undo the change."""
    op.drop_table("observation_signals")
