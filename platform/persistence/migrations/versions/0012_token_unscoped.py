"""Give a token its own flag for standing in for the person who holds it.

Before this, an empty ``scopes`` list meant two different things depending on
who issued the token, and nothing on the row said which: a machine token
issued with no scope chosen and a browser sign-in both stored the same empty
array, and the application told them apart only by which code path had issued
them. ``unscoped`` makes that a stored fact instead of an assumption — `False`
for a token that names what it may do, `True` for one that stands in for its
owner and keeps resolving to whatever that owner currently holds.

**The backfill matches two fixed descriptions, never a name.** A browser
sign-in and the durable credential issued right after the bootstrap one are
the only two callers that have ever asked for ``unscoped=True``, and both
write a constant ``description`` no request body chooses — unlike the durable
credential's own *name*, which ``POST /first-run/durable-credential`` takes
from whoever calls it. Matching on the description a caller cannot set is what
keeps a deployment where an operator picked their own name for that credential
from losing access the moment this migration runs.

Every other pre-existing row — every machine token issued with no scope
chosen, which is the row this whole feature exists to stop reading as "holds
everything" — gets the new column's default, `False`, exactly the reading this
feature makes correct.

Revision: 0012_token_unscoped
Parent: 0011_verifications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_token_unscoped"
down_revision = "0011_verifications"
branch_labels = None
depends_on = None

#: The two fixed, non-operator-editable descriptions a pre-existing row can
#: carry that mean "this token stands in for the person who holds it" —
#: `platform/identity/local_accounts.py`'s sign-in and
#: `platform/startup/bootstrap.py`'s `establish_durable_credential`, on the
#: day this migration was written. Repeated rather than imported, for the
#: reason every migration in this directory repeats rather than imports: a
#: migration describes the database on the day it ran, and a string that
#: changes later must not silently change what this did.
_UNSCOPED_DESCRIPTIONS = (
    "Issued by a local sign-in.",
    "Established from the bootstrap credential at first run.",
)


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "api_tokens",
        sa.Column("unscoped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    descriptions = "', '".join(_UNSCOPED_DESCRIPTIONS)
    op.execute(f"UPDATE api_tokens SET unscoped = true WHERE description IN ('{descriptions}')")


def downgrade() -> None:
    """Undo the change."""
    op.drop_column("api_tokens", "unscoped")
