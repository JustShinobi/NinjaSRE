"""Recording a scenario's fixtures, and regenerating them when the API moves.

The paths a scenario records are not chosen by hand. They are the paths the
shipped investigation tools *actually requested* when the scenario last ran, read
off the transport. That single decision is what keeps regeneration honest in both
directions:

- a tool that starts asking a new question produces a capture that includes it,
  so refreshing a scenario picks up the new reading rather than leaving a hole;
- a tool that stops asking an old one produces a capture that drops it, and the
  staleness check then reports the leftover recording rather than carrying it
  forever as a fixture nobody reads.

Regeneration writes one machine-owned document, ``readings.json``, beside the
hand-written declaration. Nothing rewrites the prose: a refresh should never be
able to change what a scenario claims is true, only what the cluster said.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from config.constants.hypervisor_scenarios import HYPERVISOR_READINGS_FILENAME
from tests.harness.proxmox.declaration import Scenario
from tests.harness.proxmox.laboratory import LaboratoryDriver
from tests.harness.proxmox.readings import read


class CaptureRefused(Exception):
    """A capture would have produced fixtures nothing asks for, or none at all."""


def _bare(path: str) -> str:
    """Return ``path`` without its query, which is how a recording is keyed.

    Proxmox takes a parameter on a handful of reads — SMART attributes are per
    disk — and those are recorded with the query attached. Everything else is
    keyed by the path alone, because a recording pinned to a query string stops
    matching the first time a client adds a parameter it was always entitled to
    send.
    """
    return path


async def requested_paths(scenario: Scenario) -> tuple[str, ...]:
    """Return every API path this scenario's tools ask for, deduplicated in order.

    Read from a fixture-backed run rather than declared, because the declaration
    would be a second place to keep the same fact and the two would disagree the
    first time a tool learned a new question.
    """
    readings = await read(scenario)
    seen: dict[str, None] = {}
    for path in readings.requested:
        seen.setdefault(_bare(path), None)
    return tuple(seen)


async def capture(scenario: Scenario, *, driver: LaboratoryDriver) -> dict[str, Any]:
    """Return what a live cluster answers to everything ``scenario`` asks it.

    Raises:
        CaptureRefused: the scenario's tools asked nothing, so there is nothing
            to record and the resulting fixture set would be empty and green.
    """
    paths = await requested_paths(scenario)
    if not paths:
        raise CaptureRefused(
            f"{scenario.scenario_id} runs no investigation tool, so a capture would record "
            f"nothing and the scenario would pass against an empty cluster"
        )
    return await driver.capture(paths)


def write_fixtures(scenario: Scenario, responses: dict[str, Any]) -> Path:
    """Write ``responses`` as this scenario's recorded readings, and return the path.

    Sorted keys and a trailing newline, so a regeneration that changed one
    reading produces a one-line diff rather than a reordered file nobody reviews.

    Raises:
        CaptureRefused: the scenario was loaded from nowhere, so there is no
            directory to write into.
    """
    if scenario.directory is None:
        raise CaptureRefused(
            f"{scenario.scenario_id} was built in memory rather than loaded from a directory, "
            f"so there is nowhere to write its fixtures"
        )
    path = Path(scenario.directory) / HYPERVISOR_READINGS_FILENAME
    path.write_text(json.dumps(responses, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


async def regenerate(scenario: Scenario, *, driver: LaboratoryDriver) -> Path:
    """Refresh ``scenario``'s recorded responses from a cluster, and say where.

    The whole of FR-020: when the API changes, a scenario is refreshed by running
    this rather than by reading a diff and guessing. The declaration — the cause,
    the evidence, the correct response — is untouched, because those are claims
    about the world and not readings from it.
    """
    return write_fixtures(scenario, await capture(scenario, driver=driver))


async def regenerate_all(
    scenarios: Sequence[Scenario], *, driver: LaboratoryDriver
) -> tuple[Path, ...]:
    """Refresh every scenario in ``scenarios``, returning what was written."""
    return tuple([await regenerate(scenario, driver=driver) for scenario in scenarios])


__all__ = [
    "CaptureRefused",
    "capture",
    "regenerate",
    "regenerate_all",
    "requested_paths",
    "write_fixtures",
]
