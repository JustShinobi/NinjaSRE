"""Where a scenario's readings come from, and what happens when they rot.

A recorded response that no longer matches the API produces a suite that passes
while testing nothing. That is the worst failure shape available — green, quiet,
and wrong — and it is the one this file exists to make impossible: a fixture
nothing asks for any more, or a reading the shipped tools stopped producing, is a
loud failure naming the scenario.

The laboratory half is here for the same reason. A destructive scenario that
leaves the cluster in a state the next one reads makes every result after it a
function of the damage, and a suite that carried on would report those as
measurements of the system.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.constants.hypervisor_scenarios import HYPERVISOR_READINGS_FILENAME
from tests.harness.proxmox.capture import CaptureRefused, capture, regenerate, requested_paths
from tests.harness.proxmox.declaration import (
    CorrectResponse,
    Fixtures,
    LaboratorySetup,
    ReadingsPlan,
    Scenario,
    ToolCall,
    Truth,
)
from tests.harness.proxmox.laboratory import (
    LABORATORY,
    LaboratoryCluster,
    LaboratoryNode,
    LaboratoryUnusable,
    RecordedLaboratory,
    run_destructive,
)
from tests.harness.proxmox.loader import load_scenario
from tests.harness.proxmox.readings import StaleFixture, read, verify_fresh
from tests.harness.proxmox.verdicts import ResponseKind

pytestmark = pytest.mark.synthetic

CORPUS = Path(__file__).parent / "proxmox"
A_QUORUM_SCENARIO = CORPUS / "quorum" / "q1-node-unreachable-quorum-lost"


def a_scenario(**changes: object) -> Scenario:
    """Return a loadable scenario built in memory, with ``changes`` applied."""
    defaults: dict[str, object] = {
        "scenario_id": "probe",
        "domain": "quorum",
        "title": "a probe scenario",
        "situation": "the reference cluster, healthy, read by the quorum tool.",
        "truth": Truth(root_cause="none", evidence=("quorate",)),
        "response": CorrectResponse(kind=ResponseKind.NONE, why="nothing is wrong"),
        "readings": ReadingsPlan(
            tools=(ToolCall(name="proxmox_quorum_status"),),
            must_report=('"quorate": true',),
        ),
    }
    defaults.update(changes)
    return Scenario(**defaults)  # type: ignore[arg-type]


# -- T-008: the laboratory --------------------------------------------------


def test_the_laboratory_is_a_two_node_cluster_with_a_named_known_state() -> None:
    """The failures worth measuring here are the ones a majority would hide."""
    assert len(LABORATORY.nodes) == 2
    assert LABORATORY.known_state
    assert not LABORATORY.quorum_device


def test_a_laboratory_with_a_comfortable_majority_is_refused() -> None:
    with pytest.raises(ValueError, match="two-node cluster"):
        LaboratoryCluster(
            name="too-many",
            nodes=tuple(
                LaboratoryNode(name=f"lab{index}", address=f"10.0.0.{index}") for index in (1, 2, 3)
            ),
            known_state="baseline",
        )


def test_a_laboratory_with_nothing_to_restore_to_is_refused() -> None:
    with pytest.raises(ValueError, match="restored to"):
        LaboratoryCluster(
            name="no-way-back",
            nodes=(
                LaboratoryNode(name="lab01", address="10.0.0.1"),
                LaboratoryNode(name="lab02", address="10.0.0.2"),
            ),
            known_state="  ",
        )


# -- T-009: capture ---------------------------------------------------------


async def test_a_capture_records_exactly_the_paths_the_shipped_tools_asked_for() -> None:
    """Chosen by the tools rather than by hand, so a tool that learns a new
    question produces a capture that includes it."""
    scenario = a_scenario()

    asked = await requested_paths(scenario)

    assert "/cluster/status" in asked
    assert len(set(asked)) == len(asked)


async def test_a_capture_answers_every_path_the_run_requested() -> None:
    captured = await capture(a_scenario(), driver=RecordedLaboratory())

    assert "/cluster/status" in captured


async def test_a_scenario_that_reads_nothing_cannot_be_captured() -> None:
    """An empty fixture set is a scenario that passes against an empty cluster."""
    with pytest.raises(CaptureRefused, match="runs no investigation tool"):
        await capture(a_scenario(readings=ReadingsPlan()), driver=RecordedLaboratory())


# -- T-010: regeneration ----------------------------------------------------


async def test_regeneration_writes_the_recorded_readings_beside_the_declaration(
    tmp_path: Path,
) -> None:
    """FR-020: refreshing a scenario is running a command, not an archaeology
    project — and it rewrites only the machine-owned half."""
    directory = tmp_path / "probe"
    directory.mkdir()
    declaration = (A_QUORUM_SCENARIO / "proxmox-scenario.yml").read_text(encoding="utf-8")
    (directory / "proxmox-scenario.yml").write_text(declaration, encoding="utf-8")
    scenario, _ = load_scenario(directory)

    written = await regenerate(scenario, driver=RecordedLaboratory())

    assert written.name == HYPERVISOR_READINGS_FILENAME
    assert "/cluster/status" in json.loads(written.read_text(encoding="utf-8"))
    assert (directory / "proxmox-scenario.yml").read_text(encoding="utf-8") == declaration


async def test_a_regenerated_scenario_still_loads_and_still_reads(tmp_path: Path) -> None:
    directory = tmp_path / "probe"
    directory.mkdir()
    (directory / "proxmox-scenario.yml").write_text(
        (A_QUORUM_SCENARIO / "proxmox-scenario.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    scenario, _ = load_scenario(directory)
    await regenerate(scenario, driver=RecordedLaboratory())

    reloaded, _ = load_scenario(directory)

    assert (await read(reloaded)).entries


# -- T-011: a fixture that no longer matches the API ------------------------


async def test_a_reading_the_shipped_tools_no_longer_produce_fails_loudly() -> None:
    """SC-012, NFR-004. Scoring against stale data is worse than not scoring."""
    scenario = a_scenario(
        readings=ReadingsPlan(
            tools=(ToolCall(name="proxmox_quorum_status"),),
            must_report=("the quorum device is contributing four votes",),
        )
    )

    readings = await read(scenario)

    assert readings.missing
    with pytest.raises(StaleFixture, match="no longer report"):
        verify_fresh(readings)


async def test_a_recorded_response_nothing_asks_for_any_more_fails_loudly() -> None:
    """The other half of the same divergence, and the half that decays quietly."""
    scenario = a_scenario(
        fixtures=Fixtures(responses={"/cluster/config/qdevice-that-was-renamed": {"votes": 1}})
    )

    readings = await read(scenario)

    assert readings.unused_fixtures == ("/cluster/config/qdevice-that-was-renamed",)
    with pytest.raises(StaleFixture, match="nothing requested"):
        verify_fresh(readings)


async def test_a_scenario_naming_a_tool_this_repository_no_longer_ships_fails_loudly() -> None:
    scenario = a_scenario(readings=ReadingsPlan(tools=(ToolCall(name="proxmox_force_quorum"),)))

    with pytest.raises(StaleFixture, match="not a Proxmox investigation tool"):
        await read(scenario)


async def test_the_shipped_corpus_readings_are_fresh() -> None:
    """The check applied to the real thing, which is where it earns its keep."""
    scenario, _ = load_scenario(A_QUORUM_SCENARIO)

    verify_fresh(await read(scenario))


# -- T-044: restore between destructive scenarios ---------------------------


def a_destructive(scenario_id: str, fault: str) -> Scenario:
    """Return a scenario that runs against the laboratory and breaks it."""
    return a_scenario(
        scenario_id=scenario_id,
        modes=("fixture", "laboratory"),
        laboratory=LaboratorySetup(fault=fault, restore="roll back to scenario-baseline"),
    )


async def test_the_cluster_is_restored_between_destructive_scenarios() -> None:
    """NFR-002. The second scenario must not be reading the first one's damage."""
    driver = RecordedLaboratory()
    scenarios = (a_destructive("d1", "pull the link"), a_destructive("d2", "fill the thin pool"))

    outcomes = await run_destructive(scenarios, driver=driver)

    assert [found.scenario_id for found in outcomes] == ["d1", "d2"]
    assert driver.applied == ["pull the link", "fill the thin pool"]
    assert driver.restores == [LABORATORY.known_state] * 2
    assert all(found.after_restore.usable for found in outcomes)


async def test_a_scenario_that_leaves_the_cluster_unusable_is_recovered_from() -> None:
    """A cluster that needs a second rollback is ordinary; the suite carries on."""
    driver = RecordedLaboratory(stubborn=frozenset({"pull the link"}))

    outcomes = await run_destructive((a_destructive("d1", "pull the link"),), driver=driver)

    assert outcomes[0].recovered
    assert outcomes[0].after_restore.usable
    assert driver.restores == [LABORATORY.known_state] * 2


async def test_a_laboratory_that_does_not_come_back_stops_the_run_naming_the_scenario() -> None:
    """Carrying on would report measurements of a broken cluster as measurements
    of the system."""
    driver = RecordedLaboratory(unrecoverable=frozenset({"destroy the pool"}))
    scenarios = (a_destructive("d1", "destroy the pool"), a_destructive("d2", "pull the link"))

    with pytest.raises(LaboratoryUnusable, match="d1"):
        await run_destructive(scenarios, driver=driver)

    assert driver.applied == ["destroy the pool"]
