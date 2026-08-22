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
from sqlalchemy.exc import DBAPIError, InvalidRequestError

from platform.persistence.postgres.graph.bootstrap import load

pytestmark = pytest.mark.unit


class _Refusal(DBAPIError):
    """What asyncpg raises when a role may not load a library."""

    def __init__(self) -> None:
        super().__init__('LOAD "age"', None, Exception('access to library "age" is not allowed'))


class _Savepoint:
    """Undoes what happened inside it and leaves the outer transaction open."""

    async def __aenter__(self) -> _Savepoint:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakeConnection:
    """A connection that refuses ``LOAD`` and answers whatever else is scripted."""

    def __init__(self, *, age_usable: bool) -> None:
        self._age_usable = age_usable
        self.statements: list[str] = []
        self.rolled_back = 0
        self.savepoints = 0

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

    def begin_nested(self) -> _Savepoint:
        self.savepoints += 1
        return _Savepoint()


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


async def test_the_refused_statement_is_undone_before_anything_else_runs() -> None:
    """A refused statement poisons the transaction; the probe after it needs a clean one.

    Undone with a savepoint rather than a rollback. The transaction is not this
    function's to end — ``ensure`` opened it — and rolling it back is what left
    the probe emitting statements into a closed one.
    """
    conn = FakeConnection(age_usable=True)

    await load(conn)  # type: ignore[arg-type]

    assert conn.savepoints == 2, "the refusal and the probe after it are each contained"
    assert conn.rolled_back == 0, "the transaction belongs to the caller"


class OuterTransactionConnection:
    """A connection whose transaction belongs to an ``engine.begin()`` block.

    This is the shape ``ensure`` actually passes in, and it is the one the
    plain fake above cannot express. SQLAlchemy lets the block own the
    transaction: rolling back from inside closes it, and every statement after
    that raises ``InvalidRequestError`` — not the database error the caller is
    catching — so the refusal handling never gets to run and the bring-up dies
    on an exception nothing was looking for.

    A savepoint is the operation that is legal here. It undoes the refused
    statement and leaves the surrounding transaction open, which is what the
    probe after it needs.
    """

    def __init__(self, *, age_usable: bool) -> None:
        self._age_usable = age_usable
        self._closed = False
        self.statements: list[str] = []
        self.savepoints = 0

    def _guard(self) -> None:
        if self._closed:
            raise InvalidRequestError(
                "Can't operate on closed transaction inside context manager. "
                "Please complete the context manager before emitting further commands."
            )

    async def execute(self, statement: object) -> object:
        self._guard()
        rendered = str(statement)
        self.statements.append(rendered)
        if rendered.startswith("LOAD"):
            raise _Refusal()
        if not self._age_usable:
            raise _Refusal()
        return object()

    async def scalar(self, statement: object, *args: object) -> object:
        self._guard()
        self.statements.append(str(statement))
        if not self._age_usable:
            raise _Refusal()
        return 1

    async def rollback(self) -> None:
        self._closed = True

    def begin_nested(self) -> _Savepoint:
        self.savepoints += 1
        return _Savepoint()


async def test_a_refused_load_is_survivable_inside_a_transaction_someone_else_owns() -> None:
    """The deployment case: ``ensure`` holds the transaction, so a rollback is not ours to make.

    Without this, a refused ``LOAD`` on a correctly-configured database ends the
    process with ``InvalidRequestError`` instead of reporting that AGE is there
    — and the deployment never starts at all, which is a worse answer than the
    wrong one this module was written to avoid.
    """
    conn = OuterTransactionConnection(age_usable=True)

    assert await load(conn) is True  # type: ignore[arg-type]
    assert conn.savepoints, "the refusal was not contained in a savepoint"


async def test_a_genuine_absence_is_still_reported_from_inside_that_transaction() -> None:
    """The other half, in the same shape: no AGE behind the refusal is still no AGE."""
    conn = OuterTransactionConnection(age_usable=False)

    assert await load(conn) is False  # type: ignore[arg-type]
