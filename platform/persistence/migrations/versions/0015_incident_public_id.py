"""Give every incident a short, URL-safe address distinct from its primary key.

Before this, the only identifier an incident had was its primary key —
``<correlation key>@<opened-at, to the microsecond>``, shortened to a digest
when it ran past the column's width. That is exactly the shape a primary key
should have and exactly the shape a URL should not: it carries ``:``, ``@``
and sometimes ``+``, none of which a URL segment may carry unescaped, and
every one of them was reaching a browser's address bar percent-encoded.

``public_id`` is a second, short address for the same row — a digest of the
primary key, prefixed so the edge can tell an incident's address apart from a
run's own without a database round trip. It does not replace the primary
key: the timeline still references ``incident_id``, correlation still keys
on it, and an operator debugging from the database can still paste it into
the address bar and have the incident open. What changes is what the console
*emits*: a link a person can copy, contact-free of everything a URL would
otherwise have to escape.

**The backfill imports the derivation instead of repeating it**, breaking
this directory's own usual convention of writing each migration's logic
inline so it keeps describing the schema on the day it ran even if the
calling code later changes. That convention exists for values a caller
chooses — a token's description, a boolean flag — where a later rename would
silently change what an old migration meant. A digest is not that: the whole
point of ``public_id`` is that the value a migration backfills and the value
the code computes for the same row must be the identical string forever, and
a second, hand-copied implementation of the digest inside this file is
exactly how that guarantee breaks the first time somebody touches one copy
and not the other. Importing is what keeps the two from being two.

Three steps in one revision, because the middle one only makes sense between
the other two: the column arrives nullable, every existing row is backfilled
with the derivation applied to its own ``incident_id``, and only then does
the column become required and the unique index land — a ``NOT NULL``
added before the backfill would refuse the ALTER on any table that already
has rows.

Revision: 0015_incident_public_id
Parent: 0014_timeline_evidence
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from platform.persistence.ports.incident_store import public_incident_id

revision = "0015_incident_public_id"
down_revision = "0014_timeline_evidence"
branch_labels = None
depends_on = None

#: Long enough for the prefix plus the digest width `public_incident_id`
#: produces, matching `platform.persistence.postgres.models.ID_LENGTH` —
#: repeated rather than imported because a migration's column width is a
#: fact about the schema on the day it ran, and the ORM model is free to
#: change that constant later without rewriting history.
_PUBLIC_ID_COLUMN_LENGTH = 128


def upgrade() -> None:
    """Apply the change."""
    op.add_column(
        "incidents",
        sa.Column("public_id", sa.String(length=_PUBLIC_ID_COLUMN_LENGTH), nullable=True),
    )

    connection = op.get_bind()
    incidents = sa.table(
        "incidents",
        sa.column("org_id", sa.String),
        sa.column("incident_id", sa.String),
        sa.column("public_id", sa.String),
    )
    rows = connection.execute(sa.select(incidents.c.org_id, incidents.c.incident_id)).fetchall()
    for org_id, incident_id in rows:
        connection.execute(
            incidents.update()
            .where(incidents.c.org_id == org_id, incidents.c.incident_id == incident_id)
            .values(public_id=public_incident_id(incident_id))
        )

    op.alter_column("incidents", "public_id", nullable=False)
    op.create_index("ix_incidents_public_id", "incidents", ["org_id", "public_id"], unique=True)


def downgrade() -> None:
    """Undo the change.

    Drops the index and the column, and nothing else. No incident is
    deleted, no other column is touched, and the primary key — ``incident_id``
    — is never written by this migration in either direction, so a downgrade
    followed by an upgrade backfills the identical values it started with.
    """
    op.drop_index("ix_incidents_public_id", table_name="incidents")
    op.drop_column("incidents", "public_id")
