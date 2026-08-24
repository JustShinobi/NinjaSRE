"""Let more than one principal in a deployment have no email address.

Before this, ``email_folded`` was ``NOT NULL`` and every principal with no
address stored the empty string there — including the bootstrap service
account every deployment creates at first start. The unique index on
``(org_id, email_folded)`` therefore treated "no address" as a value like any
other, and the first attempt to create a second addressless principal in the
same organisation collided with it: a raw uniqueness violation, on a column
nobody creating that second principal ever meant to fill in.

The column becomes nullable, and the dobra ("no address") becomes ``NULL``
instead of ``""``. PostgreSQL's own unique index never treats two ``NULL``s
as a collision, so this is the whole fix: no partial index, no sentinel
address that would then look like a real one to a query or a screen.

Reversible in the sense that matters: nothing is destroyed either way. Going
back re-widens every ``NULL`` back to ``""`` and restores the ``NOT NULL``
constraint — which only succeeds if no organisation holds more than one
addressless principal, because two rows both becoming ``""`` in the same
organisation is exactly the collision this revision exists to stop being
possible. When that is not the case, the downgrade refuses and names the
principals an operator would need to give an address to (all but one) before
the schema could go back.

Revision: 0019_users_email_optional
Parent: 0018_local_sign_in_opening
"""

from __future__ import annotations

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0019_users_email_optional"
down_revision = "0018_local_sign_in_opening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the change.

    The column has to become nullable *before* anything writes ``NULL`` into
    it — reversed, the fold below is a write of ``NULL`` into a column still
    declared ``NOT NULL``, which PostgreSQL refuses. A database with no
    addressless principal never took the failing path, which is exactly how
    this order shipped unnoticed: the first deployment that had one row with
    ``email_folded = ''`` failed to migrate at all.
    """
    op.alter_column("users", "email_folded", nullable=True)

    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("org_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("email_folded", sa.String),
    )
    connection.execute(users.update().where(users.c.email_folded == "").values(email_folded=None))


def downgrade() -> None:
    """Undo the change, or refuse naming what stands in the way.

    Raises rather than picking a survivor when an organisation holds more
    than one addressless principal: choosing one to keep the empty string and
    silently renaming the rest is a decision about somebody's account that a
    migration does not get to make on an operator's behalf.
    """
    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("org_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("email_folded", sa.String),
    )
    rows = connection.execute(
        sa.select(users.c.org_id, users.c.user_id).where(users.c.email_folded.is_(None))
    ).fetchall()

    by_org: dict[str, list[str]] = defaultdict(list)
    for org_id, user_id in rows:
        by_org[org_id].append(user_id)

    blocking = {org_id: sorted(ids) for org_id, ids in by_org.items() if len(ids) > 1}
    if blocking:
        detail = "; ".join(
            f"organisation {org_id!r}: {', '.join(ids)}" for org_id, ids in sorted(blocking.items())
        )
        raise RuntimeError(
            "cannot restore email uniqueness: the following organisations hold more "
            f"than one principal with no address ({detail}). Give every principal but "
            "one, in each organisation listed, an address of its own, then run this "
            "downgrade again."
        )

    connection.execute(users.update().where(users.c.email_folded.is_(None)).values(email_folded=""))
    op.alter_column("users", "email_folded", nullable=False)
