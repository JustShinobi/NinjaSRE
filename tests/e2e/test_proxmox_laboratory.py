"""The destructive suite as ``pytest`` sees it: declarative everywhere, real rarely.

What runs on every machine is the part that needs nothing — that every
destructive scenario says how the cluster is restored, that every hypervisor
write has a rehearsal, and that the restore path itself works against the
recorded stand-in. Those are the checks that catch a broken declaration on the
pull request rather than the evening before a release, with a cluster half
rebuilt.

What needs a laboratory is the execution, and it skips with a sentence saying
what to set.
"""

from __future__ import annotations

import pytest

from config.constants.hypervisor_scenarios import (
    SCENARIO_MODE_FIXTURE,
    SCENARIO_MODE_LABORATORY,
)
from tests.e2e.proxmox.rehearsal import (
    REHEARSALS,
    Rehearsal,
    rehearsal_for,
    unknown_rehearsals,
    unrehearsed,
)
from tests.e2e.proxmox.suite import destructive_scenarios, run_laboratory, skip_reason
from tests.harness.proxmox.declaration import declared_capabilities
from tests.harness.proxmox.laboratory import (
    LABORATORY,
    LaboratoryUnusable,
    RecordedLaboratory,
)

pytestmark = pytest.mark.e2e

LABORATORY_SKIP = skip_reason()


# -- what runs everywhere -----------------------------------------------------


def test_every_hypervisor_write_has_a_laboratory_rehearsal() -> None:
    """T-046. An action never run against hardware is not one to run unattended."""
    assert not unrehearsed()
    assert not unknown_rehearsals()
    assert {found.capability for found in REHEARSALS} == declared_capabilities()


def test_every_rehearsal_says_what_it_arranges_expects_and_restores() -> None:
    """A rehearsal with no restore can be run once."""
    for found in REHEARSALS:
        assert found.given.strip() and found.arrange.strip()
        assert found.expects.strip() and found.restore.strip()


def test_a_rehearsal_cannot_be_written_without_a_way_back() -> None:
    with pytest.raises(ValueError, match="restore is blank"):
        Rehearsal(
            capability="proxmox_stop_guest",
            target="ct:9105",
            given="it is running",
            arrange="start it",
            expects="it stops",
            restore="   ",
        )


def test_a_capability_with_no_rehearsal_is_named_when_it_is_asked_for() -> None:
    with pytest.raises(KeyError, match="never been run against real hardware"):
        rehearsal_for("proxmox_force_quorum")


def test_every_destructive_scenario_declares_its_fault_and_its_restore() -> None:
    scenarios = destructive_scenarios()

    assert scenarios
    for scenario in scenarios:
        assert scenario.laboratory is not None
        assert scenario.laboratory.fault.strip()
        assert scenario.laboratory.restore.strip()


async def test_the_suite_runs_against_the_recorded_stand_in_and_says_it_was_simulated() -> None:
    """FR-004, T-045. The number is only usable if it says what produced it."""
    report = await run_laboratory()

    assert report.mode == SCENARIO_MODE_FIXTURE
    assert not report.real
    assert report.simulated_scenarios
    assert not report.real_scenarios
    assert "every scenario below was simulated" in report.describe()
    assert all(found.mode == SCENARIO_MODE_FIXTURE for found in report.scenarios)


async def test_the_stand_in_run_rehearses_every_write() -> None:
    report = await run_laboratory()

    assert {found.capability for found in report.rehearsals} == declared_capabilities()
    assert all(found.performed for found in report.rehearsals)


async def test_a_scenario_that_leaves_the_cluster_unusable_stops_the_run() -> None:
    """NFR-002's failure mode: carrying on would measure a broken cluster."""
    scenarios = destructive_scenarios()
    fault = scenarios[0].laboratory.fault if scenarios[0].laboratory else ""
    driver = RecordedLaboratory(unrecoverable=frozenset({fault}))

    with pytest.raises(LaboratoryUnusable, match=scenarios[0].scenario_id):
        await run_laboratory(driver=driver)


async def test_a_cluster_that_needs_a_second_rollback_is_recovered_from() -> None:
    scenarios = destructive_scenarios()
    fault = scenarios[0].laboratory.fault if scenarios[0].laboratory else ""
    driver = RecordedLaboratory(stubborn=frozenset({fault}))

    report = await run_laboratory(driver=driver)

    assert any(found.recovered for found in report.scenarios)


# -- what needs the laboratory ------------------------------------------------


@pytest.mark.skipif(bool(LABORATORY_SKIP), reason=LABORATORY_SKIP or "laboratory configured")
async def test_the_destructive_scenarios_run_against_the_real_cluster() -> None:
    """SC-013, T-043. Only here, and only when somebody said which cluster."""
    report = await run_laboratory()

    assert report.mode == SCENARIO_MODE_LABORATORY
    assert report.real_scenarios
    assert not report.simulated_scenarios
    assert all(found.after_restore.usable for found in report.scenarios)
    assert LABORATORY.name in report.describe()


@pytest.mark.skipif(bool(LABORATORY_SKIP), reason=LABORATORY_SKIP or "laboratory configured")
async def test_every_hypervisor_write_is_run_once_against_the_real_cluster() -> None:
    """T-046 in execution rather than in declaration."""
    report = await run_laboratory()
    performed = {found.capability for found in report.rehearsals if found.performed}

    assert performed == declared_capabilities()
    assert all(found.mode == SCENARIO_MODE_LABORATORY for found in report.rehearsals)
