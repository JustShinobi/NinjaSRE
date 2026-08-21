"""AGE refusing a ``LOAD`` is not the same fact as AGE being unavailable.

``LOAD`` is a superuser-only command unless the library sits in
``$libdir/plugins``, and a PostgreSQL that carries Apache AGE commonly puts it
in ``shared_preload_libraries`` instead — precisely so that no session has to
load it and no application needs a superuser to run one. A deployment shaped
that way is the *good* shape, and reading the refusal as "this database has no
graph" reports it as broken.

The distinction matters at exactly one moment and it is an expensive one: the
health endpoint decides whether a deployment is ready, and a blast radius is
what an investigation loses when the graph is declared missing.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import DBAPIError

from platform.persistence.postgres.graph.bootstrap import load

pytestmark = pytest.mark.unit


class _Refusal(DBAPIError):
    """What asyncpg raises when a role may not load a library."""

    def __init__(self) -> None:
        super().__init__('LOAD "age"', None, Exception('access to library "age" is not allowed'))


class FakeConnection:
    """A connection that refuses ``LOAD`` and answers whatever else is scripted."""

    def __init__(self, *, age_usable: bool) -> None:
        self._age_usable = age_usable
        self.statements: list[str] = []
        self.rolled_back = 0

    async def execute(self, statement: object) -> object:
        rendered = str(statement)
        self.statements.append(rendered)
        if rendered.startswith("LOAD"):
            raise _Refusal()
        if not self._age_usable:
            raise _Refusal()
        return object()

    async def scalar(self, statement: object, *args: object) -> object:
        rendered = str(statement)
        self.statements.append(rendered)
        if not self._age_usable:
            raise _Refusal()
        return 1

    async def rollback(self) -> None:
        self.rolled_back += 1


async def test_a_refused_load_still_reports_age_when_it_is_preloaded() -> None:
    """The deployment this exists for: AGE in ``shared_preload_libraries``.

    Nothing needs loading, the role is not a superuser, and Cypher runs
    perfectly. Saying the graph is unavailable here takes the blast radius away
    from every investigation on a deployment that was configured correctly.
    """
    conn = FakeConnection(age_usable=True)

    assert await load(conn) is True  # type: ignore[arg-type]
    assert any(s.startswith("LOAD") for s in conn.statements), "the load is still attempted first"


async def test_a_refused_load_with_no_age_behind_it_is_still_a_refusal() -> None:
    """The other half: a database that genuinely has no AGE reports none.

    Without this the change would turn every real absence into a false yes,
    which is the failure mode that only shows up during an incident.
    """
    conn = FakeConnection(age_usable=False)

    assert await load(conn) is False  # type: ignore[arg-type]


async def test_the_failed_transaction_is_rolled_back_before_anything_else_runs() -> None:
    """A refused statement poisons the transaction; the probe after it needs a clean one."""
    conn = FakeConnection(age_usable=True)

    await load(conn)  # type: ignore[arg-type]

    assert conn.rolled_back == 1
