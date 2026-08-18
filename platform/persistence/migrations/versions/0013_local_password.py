"""Give a person a place to keep a local passphrase, apart from the environment-configured account.

Before this, exactly one account could ever sign in with a name and a
passphrase: the environment-configured one (``LOCAL_ACCOUNT_PASSWORD_HASH_ENV``),
verified in the process against a hash that never touches this table at all.
A deployment creating a second, third, or fortieth local account needs
somewhere to keep each one's own hash, and it needs to be a column nothing
but a dedicated write path ever touches — the existing ``users`` upsert
already updates every other column on every call, and a password hash caught
in that path would be cleared by the next unrelated edit.

Nullable, and starts empty for every existing row. A principal signs in
through an identity provider, through the one environment-configured
account, or through a passphrase this column holds — the first two never
write it, and a deployment with neither in use for a given person simply has
``NULL`` here, which is not a state anything currently reads as a working
credential.

Revision: 0013_local_password
Parent: 0012_token_unscoped
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_local_password"
down_revision = "0012_token_unscoped"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "users",
        sa.Column("local_password_hash", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    """Undo the change."""
    op.drop_column("users", "local_password_hash")
