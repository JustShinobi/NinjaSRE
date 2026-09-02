"""One expired decision may hold one live replacement, and the database says so.

Reproposing an expired approval has to be idempotent: two clicks, one new
proposal. Until now the only thing holding that was a lookup the route ran
before queueing, and a lookup cannot see a row another transaction has not
committed yet. Two calls landing together both read "nothing reproposed yet",
both queue, and the reviewer is left with two live proposals for one lapsed
decision — the second of which nobody can tell apart from the first.

A partial unique index over ``(org_id, arguments->>'origin_approval_id')``
closes it, because the second insert has to *block* on the first rather than
read past it. It is expressible only because the marker now reaches the store
in the statement that creates the request; while it was written by a later
amendment there was a committed pending row carrying nothing, which no
constraint on that key could have seen at all.

**Partial on ``state = 'pending'``**, and that is the load-bearing half. An
unconditional rule would make an origin unreproposable for ever once its first
replacement lapsed in its turn — the second expiry could never be answered by
anyone, which is worse than the duplicate this prevents. Only a live row
occupies its origin; an approved, rejected, expired or discarded one has
nothing outstanding and stands aside.

The key is also partial on the marker being present, which keeps the index to
the reproposals rather than the whole approval queue. Ordinary changes write no
``origin_approval_id`` at all — absent, never null — so nothing else is enrolled
in a rule meant for these.

**If the upgrade fails, it is telling you something true.** ``CREATE UNIQUE
INDEX`` refuses when the data already violates it, and the only thing that could
have produced two live proposals for one origin is the race this closes. The
error names the duplicated origin; discard one of the two proposals
(``POST /v1/approvals/{approval_id}/discard``) and run it again. Choosing one to
withdraw is a decision about somebody's pending approval, and a migration is the
wrong place to make it silently.

Revision: 0022_pending_origin_unique
Parent: 0021_estate_daily_snapshot
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_pending_origin_unique"
down_revision = "0021_estate_daily_snapshot"
branch_labels = None
depends_on = None

_INDEX = "ix_approvals_pending_origin"

#: The key a reproposal records its origin under, spelled the way
#: ``platform.persistence.ports.approval_store.ORIGIN_APPROVAL_ID_KEY`` spells
#: it. Repeated rather than imported, the convention this directory keeps for a
#: value a caller chooses: a later rename must not silently change what an
#: already-applied migration built.
_ORIGIN_KEY = "origin_approval_id"

_MARKER = f"(arguments ->> '{_ORIGIN_KEY}')"

#: Live rows carrying a marker, and nothing else.
_LIVE_REPROPOSALS = f"state = 'pending' AND {_MARKER} IS NOT NULL"


def upgrade() -> None:
    """Apply the change."""
    op.create_index(
        _INDEX,
        "approvals",
        ["org_id", sa.text(_MARKER)],
        unique=True,
        postgresql_where=sa.text(_LIVE_REPROPOSALS),
    )


def downgrade() -> None:
    """Undo the change.

    Drops the index and nothing else. No row is written in either direction, so
    a downgrade followed by an upgrade rebuilds the identical index over the
    identical rows.
    """
    op.drop_index(_INDEX, table_name="approvals")
