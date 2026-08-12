"""The zones an operator confirmed in a preview, carried into the sweep.

The defect this covers: ``POST /v1/estate/discovery/sources`` takes a zone map,
uses it to render the preview, and then registers a job that does not carry it.
The preview said which zone every guest was in; the recurring sweep that
actually fills the estate placed none of them, because the map was dropped
between confirming and scheduling.

On a real cluster that is the difference between an estate somebody can filter
and a flat list of a hundred rows.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.estate.discovery.schedule import PAYLOAD_ZONES, sweep_job, zones_of

pytestmark = pytest.mark.unit


class _Declaration:
    integration = "proxmox"
    interval_seconds = 300


def test_the_job_carries_the_zones_it_was_registered_with() -> None:
    job = sweep_job(
        _Declaration(),  # type: ignore[arg-type]
        next_run_at=datetime.now(UTC),
        source="proxmox",
        zones={"10.20.30.0/24": "apps", "10.20.20.0/24": "infra"},
    )

    assert job.payload[PAYLOAD_ZONES] == {
        "10.20.30.0/24": "apps",
        "10.20.20.0/24": "infra",
    }


def test_a_registration_with_no_zones_carries_none_rather_than_an_empty_map() -> None:
    """A deployment that declared no networks sweeps and places nothing, which
    is the documented degradation rather than a refusal."""
    job = sweep_job(
        _Declaration(),  # type: ignore[arg-type]
        next_run_at=datetime.now(UTC),
        source="proxmox",
    )

    assert PAYLOAD_ZONES not in job.payload


def test_the_map_comes_back_out_of_the_payload_the_sweep_reads() -> None:
    """What the runner asks for, in the shape the enrichment plan wants."""
    declared = {"10.20.40.0/24": "dmz"}

    assert zones_of({PAYLOAD_ZONES: declared}) == declared
    assert zones_of({}) == {}
    # A payload written by an older release, or by hand, must not raise.
    assert zones_of({PAYLOAD_ZONES: "not a map"}) == {}
