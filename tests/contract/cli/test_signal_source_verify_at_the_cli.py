"""``ninjasre integrations verify --report``, against the route that answers it.

Two facts a credential check cannot establish, and both of them decide whether
an investigation that reaches this source will say anything true: is the store
holding data for a recent window, and does its clock agree with the platform's.
The gateway measures them; these assertions are that they survive the trip to a
terminal, in words rather than as a status.

The application is the real one, the route is the real one, and the client is
the real ``RemoteClient`` opening what it would open over the network. What is
scripted is the vendor's answer, because the point of the flag is to reach a
vendor and there is not one here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from config.constants.signals import (
    SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
    VERIFY_WINDOW_MINUTES,
)
from surfaces.cli.client import RemoteClient
from surfaces.cli.commands.integrations import _report_pairs
from tests.contract.cli.test_remote_client_speaks_the_api import (  # noqa: F401
    _Deployment,
    deployment,
    remote,
)

pytestmark = pytest.mark.contract

INTEGRATION = "prometheus"

#: What the framework produces for a source that is up, holding nothing, and
#: whose clock is a minute and a half ahead. Written out rather than produced
#: here, because what is under test is the *carriage* — the framework's own
#: production of it is asserted in ``tests/contract/integrations``.
DEGRADED_REPORT: dict[str, Any] = {
    "integration": INTEGRATION,
    "ok": False,
    "degraded": True,
    "degradations": [
        f"it answered and holds nothing for the last {VERIFY_WINDOW_MINUTES} minutes. "
        f"Prometheus answered and is holding no series at all for this window.",
        f"its clock is 90.0s from the platform's, outside the "
        f"{SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS:.1f}s that correlation tolerates",
    ],
    "connectivity": {
        "reachable": True,
        "detail": "Prometheus accepted the credential.",
        "status_code": 200,
    },
    "probe": "calls /api/v1/status/buildinfo",
    "permissions": [],
    "missing_permissions": [],
    "affected_capabilities": [],
    "data_window": {
        "state": "empty_window",
        "window_minutes": VERIFY_WINDOW_MINUTES,
        "rows": 0,
        "probe": "evaluates 'up' over /api/v1/query_range for the window",
        "empty_means": "broken",
        "usable": False,
        "detail": f"nothing at all over the last {VERIFY_WINDOW_MINUTES} minutes",
        "advice": "check /targets on the server before checking anything here",
    },
    "clock": {
        "state": "out_of_tolerance",
        "offset_seconds": 90.0,
        "tolerance_seconds": SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
        "source_time": "2026-08-10T12:01:30+00:00",
        "probe": "reads the Date header",
        "degraded": True,
        "detail": "the source is +90.0s from the platform's clock",
    },
}


@pytest.fixture
def reporting(deployment: _Deployment) -> _Deployment:  # noqa: F811
    """Compose a deep verifier that answers for Prometheus and nothing else."""

    async def verify(name: str) -> Mapping[str, Any] | None:
        return DEGRADED_REPORT if name == INTEGRATION else None

    deployment.state.deep_verifier = verify
    return deployment


# --- what crosses the wire ------------------------------------------------------


def test_the_vendors_own_answer_reaches_the_cli_unflattened(
    reporting: _Deployment,
    remote: RemoteClient,  # noqa: F811
) -> None:
    document = asyncio.run(remote.verify_integration_report(INTEGRATION))

    assert document is not None
    assert document["data_window"]["rows"] == 0
    assert document["clock"]["offset_seconds"] == pytest.approx(90.0)
    assert document["degradations"]


def test_a_vendor_with_nothing_further_to_be_asked_is_none_rather_than_an_error(
    reporting: _Deployment,
    remote: RemoteClient,  # noqa: F811
) -> None:
    """The route answers 404 for a working deployment, so the client must not raise."""
    assert asyncio.run(remote.verify_integration_report("datadog")) is None


def test_a_deployment_that_composed_no_deep_verifier_is_none_rather_than_empty(
    deployment: _Deployment,  # noqa: F811
    remote: RemoteClient,  # noqa: F811
) -> None:
    """An empty document would read as a clean bill of health. ``None`` does not."""
    assert deployment.state.deep_verifier is None
    assert asyncio.run(remote.verify_integration_report(INTEGRATION)) is None


# --- what a person reads --------------------------------------------------------


def test_the_terminal_names_the_empty_window_and_what_to_check() -> None:
    printed = dict(_report_pairs(DEGRADED_REPORT))

    assert f"last {VERIFY_WINDOW_MINUTES}m" in printed["Data"]
    assert "0 record(s)" in printed["Data"]
    assert "check /targets" in printed["Empty window"]


def test_the_terminal_names_the_measured_offset_and_the_tolerance() -> None:
    printed = dict(_report_pairs(DEGRADED_REPORT))

    assert "+90.0s" in printed["Clock"]
    assert f"tolerance {SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS:.1f}s" in printed["Clock"]
    assert "correlation tolerates" in printed["Degraded"]


def test_a_source_that_reports_no_clock_says_so_rather_than_showing_a_zero() -> None:
    unmeasured = dict(DEGRADED_REPORT)
    unmeasured["clock"] = {
        "state": "unreported",
        "offset_seconds": None,
        "tolerance_seconds": SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
        "source_time": None,
        "probe": "reads the Date header",
        "degraded": False,
        "detail": "this source does not report its own time",
    }

    printed = dict(_report_pairs(unmeasured))

    assert printed["Clock"] == "not reported by this source"


def test_a_deployment_that_cannot_reach_a_vendor_says_that_rather_than_nothing() -> None:
    printed = dict(_report_pairs(None))

    assert "no deep verifier is composed" in printed["Vendor report"]


def test_a_vendor_that_is_not_a_signal_source_gains_no_invented_measurement() -> None:
    """Eighty-odd integrations answer neither question, and must not appear to."""
    printed = dict(_report_pairs({"integration": "datadog", "ok": True, "degradations": []}))

    assert "Data" not in printed
    assert "Clock" not in printed
