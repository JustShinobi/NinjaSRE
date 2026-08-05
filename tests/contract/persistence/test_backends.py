"""What the suite actually ran against, said out loud.

SC-005 is "every port's contract suite passes against the Postgres
implementation, *and* an in-memory fake passes the same suite". A run that
exercised one of those has not shown it. Without this file that run looks
identical to one that showed it — same green, same count — and the difference
lives in whether somebody remembered which command they typed.
"""

from __future__ import annotations

import pytest
from conftest import POSTGRES, _postgres_backend

pytestmark = pytest.mark.contract


def test_the_run_reports_which_backends_it_covered(
    request: pytest.FixtureRequest,
    record_property: pytest.FixtureRequest,
) -> None:
    backend = _postgres_backend(request.config)
    covered = ["fakes"] + ([POSTGRES] if backend is not None else [])
    record_property("persistence-backends", ",".join(covered))  # type: ignore[operator]

    if backend is None:
        pytest.skip(
            "Ran against the in-memory fakes only. SC-005 needs both: re-run with "
            "`make test-postgres`, or set NINJASRE_TEST_DATABASE_URL, to cover the "
            "PostgreSQL implementation as well."
        )

    assert backend.url
    assert backend.source in {"docker", "NINJASRE_TEST_DATABASE_URL"}
