"""What every Postgres repository needs, in one place rather than thirteen.

Two things live here, and both are here because a copy of them in each
repository is a copy that can drift.

``TenantBound`` is the base every tenant-scoped repository shares: an
organisation and a session, and nothing else. Every query it issues filters on
``self.org_id``, which is the ``org_id`` the unit of work was opened with — a
repository has no way to obtain another, because nothing hands it one.

The rest is translation. A unique-violation from PostgreSQL is a
``DuplicateRecord``; a foreign-key violation on a tenant-scoped key is a
``RecordNotFound``, because the row it referenced does not exist *in this
tenant* and the difference is not one a caller may observe.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from platform.persistence.errors import BoundExceeded, DuplicateRecord, RecordNotFound


@dataclass(slots=True)
class TenantBound:
    """A repository bound to one organisation and one transaction."""

    org_id: str
    session: AsyncSession


def check_limit(limit: int, *, parameter: str = "limit") -> int:
    """Return ``limit``, or raise if it exceeds the page bound."""
    if limit > MAX_QUERY_PAGE_SIZE:
        raise BoundExceeded(
            parameter=parameter,
            requested=limit,
            limit=MAX_QUERY_PAGE_SIZE,
            constant="MAX_QUERY_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"{parameter} must be at least 1, got {limit}.")
    return limit


@contextmanager
def translating(
    *,
    kind: str,
    identifier: str,
    referenced: str | None = None,
    referenced_id: str | None = None,
) -> Any:
    """Turn PostgreSQL's constraint violations into this package's errors.

    A unique violation and a foreign-key violation are the two the repositories
    provoke deliberately, and each has one meaning here: the record already
    exists, or the thing it points at does not exist *in this tenant*. Anything
    else is re-raised untouched — a check constraint firing is a defect, and
    dressing it up as a duplicate would hide it.
    """
    try:
        yield
    except IntegrityError as error:
        code = getattr(getattr(error.orig, "__cause__", None), "sqlstate", None)
        if code == "23505":  # unique_violation
            raise DuplicateRecord(kind=kind, identifier=identifier) from error
        if code == "23503":  # foreign_key_violation
            # Named after the record that is *missing*, not the one that
            # referenced it. "No user with id u-ada" is actionable; "no api
            # token with id t-1" describes the row the caller just supplied.
            raise RecordNotFound(
                kind=referenced or kind, identifier=referenced_id or identifier
            ) from error
        raise


def rows_affected(result: Result[Any]) -> int:
    """Return how many rows a DML statement touched.

    ``rowcount`` is on ``CursorResult``, which is what executing an ``INSERT``,
    ``UPDATE``, or ``DELETE`` actually returns — the declared ``Result`` does
    not carry it. Narrowing here keeps one ``isinstance`` in the package rather
    than one per call site.
    """
    return int(result.rowcount) if isinstance(result, CursorResult) else 0


def utc_now() -> datetime:
    """Return the current instant, timezone-aware.

    Named for its zone rather than called ``now``, because repositories take a
    ``now`` parameter from their caller — an expiry sweep uses the caller's
    instant, not the process's — and one name for both is one shadowing bug.
    """
    return datetime.now(UTC)


def as_utc(moment: datetime | None) -> datetime | None:
    """Return ``moment`` in UTC, or ``None``.

    PostgreSQL returns ``timestamptz`` in the session time zone, which is UTC
    here but need not be in a deployment somebody configured. Normalising on the
    way out means an equality assertion in a test compares instants rather than
    representations.
    """
    if moment is None:
        return None
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def as_tuple[T](values: Iterable[T] | None) -> tuple[T, ...]:
    """Return ``values`` as a tuple, treating ``None`` as empty.

    PostgreSQL arrays come back as lists. Records in this package hold tuples,
    because a record a caller can append to is a record two callers can
    disagree about.
    """
    return () if values is None else tuple(values)


def as_list[T](values: Sequence[T]) -> list[T]:
    """Return ``values`` as the list an ``ARRAY`` column binds from."""
    return list(values)


__all__ = [
    "TenantBound",
    "as_list",
    "as_tuple",
    "as_utc",
    "check_limit",
    "rows_affected",
    "utc_now",
    "translating",
]
