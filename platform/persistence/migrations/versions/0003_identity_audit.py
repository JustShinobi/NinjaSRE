"""Scope tokens to a node, remember when they were last used, and seal the audit.

Two changes that arrive together because they are two halves of one property:
knowing who did something, and being unable to un-know it.

**Tokens gain a node, a description, and a last-use timestamp.** The node is
what makes a token narrower than the person who issued it — a bot that may act
on one team is the ordinary case, and deriving its reach from its owner's would
mean the bot was promoted whenever its owner was. The description is what makes
a token list reviewable a year later. ``last_used_at`` is what makes an
inactivity policy expressible at all; it is written coarsely, so it costs a row
update per token per day rather than per request.

**The audit table gets a trigger that refuses ``UPDATE``, ``DELETE``, and
``TRUNCATE``.** The application already has no method that could issue one. This
is the layer that still holds when somebody has a psql prompt.

Revision: 0003_identity_audit
Parent: 0002_strategies
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from platform.persistence.postgres.audit_guard import (
    AUDIT_APPEND_ONLY_DROP_STATEMENTS,
    AUDIT_APPEND_ONLY_STATEMENTS,
)

revision = "0003_identity_audit"
down_revision = "0002_strategies"
branch_labels = None
depends_on = None

#: Matches ``models.ApiToken``. Repeated rather than imported from the model,
#: because a migration describes the database on the day it ran and a model that
#: changes later must not silently change what this did.
_ID_LENGTH = 128


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "api_tokens",
        sa.Column("team_node_id", sa.String(length=_ID_LENGTH), nullable=True),
    )
    op.add_column("api_tokens", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "api_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The inactivity sweep asks "which of this tenant's tokens have not been used
    # since", which is a range scan over exactly these two columns.
    op.create_index(
        "ix_api_tokens_last_used",
        "api_tokens",
        ["org_id", "last_used_at"],
        unique=False,
    )
    # One ``execute`` per statement: asyncpg prepares whatever it is handed and
    # PostgreSQL will not prepare two commands at once.
    for statement in AUDIT_APPEND_ONLY_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """Undo the change."""
    for statement in AUDIT_APPEND_ONLY_DROP_STATEMENTS:
        op.execute(statement)
    op.drop_index("ix_api_tokens_last_used", table_name="api_tokens")
    op.drop_column("api_tokens", "last_used_at")
    op.drop_column("api_tokens", "description")
    op.drop_column("api_tokens", "team_node_id")
