"""Running the corpus: readings from the shipped tools, scores from the transcripts.

One executor, two front doors — the pytest path and the command-line path — for
the same reason the general harness has one: a suite that behaved differently
under ``pytest`` from under ``make`` would produce two numbers and no way to say
which one is the score.

The order is the point. Readings are taken first, from the real investigation
tools over the recorded responses, and checked for staleness *before* anything is
scored. A run that scored first and checked afterwards would report a number for
a scenario whose fixtures had rotted, and the number would look exactly like a
number that meant something.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from config.constants.hypervisor_scenarios import SCENARIO_MODE_FIXTURE
from tests.harness.proxmox.declaration import Scenario, scenarios_by_id
from tests.harness.proxmox.loader import discover
from tests.harness.proxmox.readings import Readings, read, verify_fresh
from tests.harness.proxmox.report import SuiteReport, report_of
from tests.harness.proxmox.scoring import score
from tests.harness.proxmox.transcripts import RecordedRun

#: Where the hypervisor corpus lives. Scenarios are directories beneath it, which
#: is what makes contributing one a matter of adding fixtures and prose.
CORPUS_ROOT: Path = Path(__file__).resolve().parents[2] / "synthetic" / "proxmox"

#: One loaded scenario and every run recorded against it.
Entry = tuple[Scenario, tuple[RecordedRun, ...]]


def load_corpus(root: Path = CORPUS_ROOT) -> tuple[Entry, ...]:
    """Return every scenario under ``root``, validated, with its recorded runs.

    Raises:
        ScenarioError: a declaration is malformed, or two share an identifier.
    """
    corpus = discover(root)
    scenarios_by_id([scenario for scenario, _ in corpus])
    return corpus


def filtered(corpus: Sequence[Entry], *, domain: str = "", scenario: str = "") -> tuple[Entry, ...]:
    """Return the entries matching every filter given, by substring."""
    selected = list(corpus)
    if domain:
        selected = [entry for entry in selected if domain in entry[0].domain]
    if scenario:
        selected = [entry for entry in selected if scenario in entry[0].scenario_id]
    return tuple(selected)


async def take_readings(corpus: Sequence[Entry], *, verify: bool = True) -> dict[str, Readings]:
    """Return each scenario's readings, refusing to go on when one has rotted.

    Raises:
        StaleFixture: a scenario's recordings and the shipped tools disagree.
    """
    taken: dict[str, Readings] = {}
    for scenario, _ in corpus:
        readings = await read(scenario)
        if verify:
            verify_fresh(readings)
        taken[scenario.scenario_id] = readings
    return taken


async def run_suite(
    root: Path = CORPUS_ROOT,
    *,
    domain: str = "",
    scenario: str = "",
    verify: bool = True,
    mode: str = SCENARIO_MODE_FIXTURE,
) -> SuiteReport:
    """Return every recorded run in the corpus, scored against its scenario."""
    started = time.perf_counter()
    corpus = filtered(load_corpus(root), domain=domain, scenario=scenario)
    readings = await take_readings(corpus, verify=verify)

    scores = [
        score(found, run, readings=readings[found.scenario_id], mode=mode)
        for found, runs in corpus
        for run in runs
    ]
    return report_of(scores, duration_seconds=time.perf_counter() - started)


__all__ = ["CORPUS_ROOT", "Entry", "filtered", "load_corpus", "run_suite", "take_readings"]
