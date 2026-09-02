"""What the incident listing asks PostgreSQL for, and where its bound lives.

Almost every dimension ``IncidentQuery`` slices by is a column, so almost every
listing is answered by SQL alone — and a listing answered by SQL alone must be
*bounded* by SQL, or a read of one page costs a read of the whole window. The
overview drains a fortnight page by page, so the difference is that window read
once against that window read twenty-five times.

``subject_id`` is the exception. It is a value inside a JSONB list, matched
after the fetch, and a ``LIMIT`` in front of it would cut away the rows it still
has to look at: the page would come back short — or empty — and nothing
downstream could tell that from an organisation that has no such incident.

The statement is the only place either claim is observable. A page-sized fixture
satisfies a bounded read and an unbounded one identically, and a fixture large
enough to tell them apart by timing would be a benchmark rather than a test, so
these two compile the query the repository builds and read the bound off it.
"""

from __future__ import annotations

import pytest

from platform.persistence.ports import IncidentQuery, IncidentState
from platform.persistence.postgres.repositories.incident_store import _statement

pytestmark = pytest.mark.contract

ORG = "acme"


def sql(query: IncidentQuery) -> str:
    """Return the SQL the listing for ``query`` compiles to."""
    return str(_statement(ORG, query, limit=query.limit))


def test_a_listing_every_filter_of_which_is_sql_is_bounded_by_sql() -> None:
    statement = sql(IncidentQuery(states=(IncidentState.OPEN,), severities=("critical",), limit=25))

    assert "LIMIT" in statement, (
        "a listing SQL can answer whole must stop at the page bound in the database: "
        f"this one reads every matching row and throws most of them away — {statement}"
    )


def test_a_listing_filtered_by_subject_is_left_unbounded_for_the_filter_behind_it() -> None:
    statement = sql(IncidentQuery(subject_id="store-cove", limit=25))

    assert "LIMIT" not in statement, (
        "the subject filter runs after the fetch, so a SQL bound would truncate the rows "
        f"it still has to see and shorten the page it produces — {statement}"
    )
