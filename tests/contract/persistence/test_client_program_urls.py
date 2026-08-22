"""``pg_dump`` and ``psql`` are libpq programs, and libpq has never heard of a driver.

Everything in this repository that holds a database URL holds SQLAlchemy's
form of it, where the scheme names the driver as well as the protocol:
``postgresql+asyncpg://``. libpq parses a URI only when the scheme is
``postgres`` or ``postgresql``, so handing it the SQLAlchemy form does not
fail loudly — it decides the whole string is a *database name* and connects to
the default unix socket instead, which on a runner with no local server reads
as ``connection to server on socket "/var/run/postgresql/.s.PGSQL.5432"
failed``. Nothing in that message mentions the URL.

The bug only appears where the client programs exist. A machine without them
runs the same command inside the container against a URL rebuilt from parts,
which is already clean — so every developer saw green and CI, which installs
the client tools, did not.
"""

from __future__ import annotations

import pytest
from postgres_backend import _libpq_url

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql+asyncpg://user:pw@127.0.0.1:5432/ninjasre",
            "postgresql://user:pw@127.0.0.1:5432/ninjasre",
        ),
        (
            "postgresql+psycopg://user:pw@host:6543/db",
            "postgresql://user:pw@host:6543/db",
        ),
        (
            "postgresql://user:pw@127.0.0.1:5432/ninjasre",
            "postgresql://user:pw@127.0.0.1:5432/ninjasre",
        ),
        ("postgres://user:pw@host/db", "postgres://user:pw@host/db"),
    ],
)
def test_a_driver_is_stripped_from_the_scheme_and_nothing_else_is(
    given: str, expected: str
) -> None:
    """Only the scheme changes: a password or a database name may contain a plus."""
    assert _libpq_url(given) == expected


def test_a_plus_after_the_scheme_is_left_alone() -> None:
    """The separator is only meaningful in the scheme, and the rest is somebody's data."""
    given = "postgresql+asyncpg://user:p+w@host:5432/db+name"

    assert _libpq_url(given) == "postgresql://user:p+w@host:5432/db+name"
