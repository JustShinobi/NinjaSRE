"""The self-check: one pass, every problem, ordered, and never a bare failure.

The property this suite exists for is FR-009's, and it is a property of the
*type* rather than of the checks: a finding cannot be constructed without both a
problem and a next action, so "connection error" is not something this module
can emit. Everything else here — the ordering, the timeouts, the single pass —
follows from checks that are independent and are allowed to be slow.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.first_run import (
    BLOCKS_EVERYTHING,
    BLOCKS_INVESTIGATION,
    BLOCKS_ONE_FEATURE,
    CHECK_CLOCK_SKEW,
    CHECK_DATABASE,
    CHECK_DISK_SPACE,
    CHECK_INVESTIGATION_RUNTIME,
    CHECK_SCHEMA,
    DEGRADES,
    MAXIMUM_CLOCK_SKEW_SECONDS,
    MINIMUM_FREE_DISK_BYTES,
    SELF_CHECK_NAMES,
)
from platform.startup.selfcheck import (
    Check,
    CheckOutcome,
    Finding,
    SelfCheckReport,
    clock_skew_check,
    disk_space_check,
    investigation_runtime_check,
    run_checks,
    store_checks,
)

pytestmark = pytest.mark.unit


# --- A finding carries an action, or it is not a finding -----------------------


def test_a_finding_needs_a_problem_and_an_action() -> None:
    """FR-009 enforced by the type. This is the whole mechanism."""
    finding = Finding(
        check=CHECK_DATABASE,
        problem="the database refused the connection",
        action="start PostgreSQL, or point NINJASRE_DATABASE_URL at one that is running",
        blocks=BLOCKS_EVERYTHING,
    )

    assert finding.problem
    assert finding.action


@pytest.mark.parametrize(
    ("problem", "action"),
    [
        ("", "start the database"),
        ("the database refused the connection", ""),
        ("   ", "start the database"),
        ("the database refused the connection", "  "),
    ],
)
def test_a_bare_failure_cannot_be_constructed(problem: str, action: str) -> None:
    """A finding that says only that something failed has moved the work."""
    with pytest.raises(ValueError, match="problem and a next action"):
        Finding(check=CHECK_DATABASE, problem=problem, action=action, blocks=BLOCKS_EVERYTHING)


def test_a_finding_must_say_how_much_it_blocks() -> None:
    with pytest.raises(ValueError, match="blocks"):
        Finding(
            check=CHECK_DATABASE,
            problem="the database refused the connection",
            action="start PostgreSQL",
            blocks="somewhat",
        )


# --- One pass, ordered by how much each finding blocks -------------------------


def _finding(check: str, blocks: str) -> Finding:
    return Finding(
        check=check,
        problem=f"{check} is not what it should be",
        action=f"fix {check}",
        blocks=blocks,
    )


def test_a_report_puts_what_blocks_the_most_first() -> None:
    """FR-008. The order is the report's whole editorial content."""
    report = SelfCheckReport(
        findings=(
            _finding("d", DEGRADES),
            _finding("c", BLOCKS_ONE_FEATURE),
            _finding("b", BLOCKS_INVESTIGATION),
            _finding("a", BLOCKS_EVERYTHING),
        )
    )

    assert [finding.check for finding in report.ordered()] == ["a", "b", "c", "d"]


def test_two_findings_of_equal_weight_come_out_in_a_stable_order() -> None:
    report = SelfCheckReport(findings=(_finding("zebra", DEGRADES), _finding("alpha", DEGRADES)))

    assert [finding.check for finding in report.ordered()] == ["alpha", "zebra"]


def test_a_report_with_no_blocking_finding_says_the_deployment_can_run() -> None:
    assert SelfCheckReport(findings=(_finding("x", DEGRADES),)).ok is True
    assert SelfCheckReport(findings=(_finding("x", BLOCKS_EVERYTHING),)).ok is False


async def test_every_check_runs_even_when_an_earlier_one_fails() -> None:
    """FR-008. One restart per problem is how ten minutes becomes an hour."""
    ran: list[str] = []

    def probe(name: str, *, fail: bool) -> Check:
        async def body() -> CheckOutcome:
            ran.append(name)
            if fail:
                return CheckOutcome.problem(
                    name, problem=f"{name} is wrong", action=f"fix {name}", blocks=BLOCKS_EVERYTHING
                )
            return CheckOutcome.fine(name, detail=f"{name} is fine")

        return Check(name=name, run=body)

    report = await run_checks(
        (probe("one", fail=True), probe("two", fail=True), probe("three", fail=False))
    )

    assert set(ran) == {"one", "two", "three"}
    assert len(report.findings) == 2
    assert len(report.passed) == 1


# --- Timeouts ------------------------------------------------------------------


async def test_an_unreachable_dependency_does_not_hang_the_check() -> None:
    """NFR-003. A check that waits forever is a check nobody ever runs twice."""

    async def never() -> CheckOutcome:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    async def quick() -> CheckOutcome:
        return CheckOutcome.fine("quick", detail="answered")

    report = await asyncio.wait_for(
        run_checks(
            (Check(name="hangs", run=never), Check(name="quick", run=quick)),
            timeout_seconds=0.05,
        ),
        timeout=5,
    )

    timed_out = next(finding for finding in report.findings if finding.check == "hangs")
    assert "did not answer" in timed_out.problem
    assert timed_out.action
    assert any(passed.check == "quick" for passed in report.passed)


async def test_a_check_that_raises_becomes_a_finding_rather_than_a_crash() -> None:
    """A self-check that dies on the first broken dependency reports nothing at
    all about the other eight, which is the opposite of what it is for."""

    async def explodes() -> CheckOutcome:
        raise RuntimeError("the socket went away")

    report = await run_checks((Check(name="boom", run=explodes),))

    finding = report.findings[0]
    assert "the socket went away" in finding.problem
    assert finding.action


async def test_a_slow_check_does_not_consume_the_time_the_others_need() -> None:
    """The checks run together. Nine sequential five-second timeouts would be
    forty-five seconds, which is past the budget on its own."""

    async def slow() -> CheckOutcome:
        await asyncio.sleep(0.2)
        return CheckOutcome.fine("slow", detail="eventually")

    started = asyncio.get_running_loop().time()
    await run_checks(tuple(Check(name=f"slow-{index}", run=slow) for index in range(8)))
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1.0, f"eight concurrent 0.2s checks took {elapsed:.2f}s"


# --- The checks themselves -------------------------------------------------------


async def test_disk_space_below_the_floor_names_the_number_and_what_to_do() -> None:
    report = await run_checks((disk_space_check(free_bytes=lambda: 1024),))

    finding = report.findings[0]
    assert finding.check == CHECK_DISK_SPACE
    assert "1024" in finding.problem or "1.0 KiB" in finding.problem
    assert str(MINIMUM_FREE_DISK_BYTES) in finding.problem or "GiB" in finding.problem
    assert finding.action


async def test_disk_space_above_the_floor_passes() -> None:
    report = await run_checks((disk_space_check(free_bytes=lambda: MINIMUM_FREE_DISK_BYTES * 4),))

    assert report.findings == ()


async def test_a_skewed_clock_is_reported_with_the_measured_difference() -> None:
    local = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
    reference = local + timedelta(seconds=MAXIMUM_CLOCK_SKEW_SECONDS * 3)

    report = await run_checks((clock_skew_check(local=lambda: local, reference=lambda: reference),))

    finding = report.findings[0]
    assert finding.check == CHECK_CLOCK_SKEW
    assert "180" in finding.problem
    assert finding.action


async def test_a_clock_within_tolerance_passes() -> None:
    local = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)

    report = await run_checks(
        (clock_skew_check(local=lambda: local, reference=lambda: local + timedelta(seconds=1)),)
    )

    assert report.findings == ()


async def test_a_store_that_is_down_blocks_everything_and_says_so() -> None:
    from platform.persistence.fakes import FakePersistence

    store = FakePersistence()
    await store.close()

    report = await run_checks(store_checks(store))

    database = next(finding for finding in report.findings if finding.check == CHECK_DATABASE)
    assert database.blocks == BLOCKS_EVERYTHING
    assert database.action


async def test_a_healthy_store_reports_the_database_and_the_schema_as_fine() -> None:
    from platform.persistence.fakes import FakePersistence

    store = FakePersistence()

    report = await run_checks(store_checks(store))

    names = {passed.check for passed in report.passed}
    assert CHECK_DATABASE in names
    assert CHECK_SCHEMA in names


# --- Coverage --------------------------------------------------------------------


def test_every_declared_check_name_is_one_the_module_can_produce() -> None:
    """The constants tier's list and the module's checks are the same list."""
    from platform.startup.selfcheck import CHECK_BUILDERS

    assert set(CHECK_BUILDERS) == set(SELF_CHECK_NAMES)


async def test_every_finding_the_check_can_produce_names_a_problem_and_an_action() -> None:
    """SC-005, over every finding rather than over a sample.

    The type already refuses a finding without both. What this adds is that
    every check is actually *driven into* its failing path, so a check whose
    failure branch was never exercised cannot hide behind the guarantee.
    """
    from platform.persistence.fakes import FakePersistence
    from platform.startup.selfcheck import deployment_checks

    down = FakePersistence()
    await down.close()

    #: Every collaborator absent, which is each check's worst case, plus a store
    #: that is down and a disk and clock that are both wrong.
    checks = deployment_checks(
        down,
        free_bytes=lambda: 0,
        reference_clock=lambda: datetime.now(UTC) + timedelta(hours=1),
    )
    report = await run_checks(checks)

    produced = {finding.check for finding in report.findings}
    assert produced == set(SELF_CHECK_NAMES) - {"integrations"}, (
        "a check declared in the constants tier produced no finding even with every "
        "collaborator absent, so its failing path is untested"
    )
    for finding in report.findings:
        assert finding.problem.strip(), f"{finding.check} named no problem"
        assert finding.action.strip(), f"{finding.check} named no action"
        assert finding.blocks in {
            BLOCKS_EVERYTHING,
            BLOCKS_INVESTIGATION,
            BLOCKS_ONE_FEATURE,
            DEGRADES,
        }


async def test_an_unusable_integration_is_reported_one_finding_at_a_time() -> None:
    """The ninth check's failing path. Separated because "no integrations
    configured" is not a problem, so it cannot be driven by absence."""
    from dataclasses import dataclass

    from platform.startup.selfcheck import integrations_check

    @dataclass(frozen=True)
    class Entry:
        integration: str
        state: str

    @dataclass(frozen=True)
    class Report:
        entries: tuple[Entry, ...]

        @property
        def unusable(self) -> tuple[Entry, ...]:
            return self.entries

    report = await run_checks(
        (
            integrations_check(
                lambda: Report(entries=(Entry("datadog", "missing"), Entry("pagerduty", "expired")))
            ),
        )
    )

    assert len(report.findings) == 2
    assert {"datadog", "pagerduty"} == {
        finding.detail["integration"] for finding in report.findings
    }
    for finding in report.findings:
        assert finding.problem and finding.action


# --- The investigation runtime -------------------------------------------------


async def test_a_deployment_with_no_investigation_runtime_says_so() -> None:
    """The one dependency that leaves no trace anywhere else.

    An account, a provider key, a resource in the estate: all of them are
    visible from a screen. A process with nothing composed to drive a ReAct
    loop looks exactly like one that has, until somebody presses Investigate
    and the run fails before it starts. The checklist carries the step; this is
    the other half, for the operator reading a diagnosis rather than a wizard.
    """
    report = await run_checks((investigation_runtime_check(None),))

    finding = report.findings[0]
    assert finding.check == CHECK_INVESTIGATION_RUNTIME
    assert finding.blocks == BLOCKS_INVESTIGATION
    assert finding.action


async def test_the_runtime_finding_never_names_a_setting_of_the_process() -> None:
    """The console reads this report.

    A finding whose text is a deploy instruction puts the environment variable
    back on the screen the failure-translation layer exists to keep it off. The
    variable belongs in the refusal the entry point raises and in the
    deployment documentation, not here.
    """
    report = await run_checks((investigation_runtime_check(None),))

    finding = report.findings[0]
    assert "NINJASRE_" not in finding.problem
    assert "NINJASRE_" not in finding.action


async def test_a_composed_runtime_passes_the_check() -> None:
    report = await run_checks((investigation_runtime_check(lambda: True),))

    assert report.findings == ()


async def test_a_runtime_that_reports_itself_absent_is_a_finding() -> None:
    """Told rather than assumed: a composition that answered no is not a pass."""
    report = await run_checks((investigation_runtime_check(lambda: False),))

    assert report.findings != ()


def test_the_runtime_check_is_one_of_the_declared_names() -> None:
    """A check nothing declares is a check no report is required to carry."""
    assert CHECK_INVESTIGATION_RUNTIME in SELF_CHECK_NAMES
