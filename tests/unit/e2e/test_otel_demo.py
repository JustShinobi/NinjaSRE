"""The demo suite: five faults, investigable end to end, with the flag put back.

All five have to be investigable, and the assertion that gives that teeth is
the last one: a
flag left on outlives the run, and the next run then investigates a demo that
was already broken and scores the agent against a fault nobody injected.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from config.constants.chaos import OTEL_DEMO_FAULT_IDS, OTEL_DEMO_FLAG_CONFIG
from tests.chaos.framework.recorded import RecordedCluster
from tests.e2e.otel_demo.faults import FAULTS_ROOT, DemoFault, discover_faults, load_fault
from tests.e2e.otel_demo.injection import FlagdFaults, FlagError
from tests.e2e.otel_demo.install import (
    DemoInstallation,
    install,
    missing_workloads,
    uninstall,
)
from tests.e2e.otel_demo.runner import expectation_of, run_faults
from tests.support.commands import CommandResult, RecordedRunner, answering
from tests.support.investigators import DerivedInvestigator, correct_answer, wrong_answer

FAULTS = discover_faults(FAULTS_ROOT)

FLAG_DOCUMENT = {
    "flags": {
        fault.flag: {"state": "ENABLED", "defaultVariant": "off", "variants": {"on": True}}
        for fault in FAULTS
    }
}


def _ticking(step: float = 40.0) -> object:
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


def _flag_runner() -> RecordedRunner:
    """Return a runner answering the flag reads and accepting the patches."""
    state = {"document": json.dumps(FLAG_DOCUMENT)}

    def read(argv: tuple[str, ...]) -> CommandResult | None:
        if "get" in argv and "configmap" in argv:
            return CommandResult(argv=argv, stdout=state["document"])
        return None

    def patch(argv: tuple[str, ...]) -> CommandResult | None:
        if "patch" in argv and "configmap" in argv:
            body = json.loads(argv[argv.index("-p") + 1])
            state["document"] = body["data"]["demo.flagd.json"]
            return CommandResult(argv=argv)
        return None

    return RecordedRunner(rules=(read, patch))


# --- installation ------------------------------------------------------------


def test_installation_is_one_command_and_names_the_stack_it_installs() -> None:
    runner = RecordedRunner(
        rules=(answering("get", "deployments", stdout=json.dumps({"items": []})),)
    )

    report = install(runner, DemoInstallation())

    assert report.installed
    assert runner.ran("helm", "upgrade", "--install", "ninjasre-otel-demo")
    assert runner.ran("--create-namespace")


def test_a_workload_that_did_not_come_up_is_named() -> None:
    document = {
        "items": [
            {
                "metadata": {"name": "ninjasre-otel-demo-cart"},
                "status": {"conditions": [{"type": "Available", "status": "True"}]},
            }
        ]
    }
    runner = RecordedRunner(rules=(answering("get", "deployments", stdout=json.dumps(document)),))

    missing = missing_workloads(runner, DemoInstallation())

    assert "cart" not in missing
    assert "flagd" in missing


def test_teardown_is_one_command_and_does_not_raise_when_it_fails() -> None:
    runner = RecordedRunner(default=CommandResult(argv=(), returncode=1, stderr="no such release"))

    result = uninstall(runner, DemoInstallation())

    assert not result.ok
    assert runner.ran("helm", "uninstall", "ninjasre-otel-demo")


# --- the five faults ---------------------------------------------------------


def test_every_declared_fault_is_on_disk_and_loads() -> None:
    assert tuple(fault.fault_id for fault in FAULTS) == tuple(sorted(OTEL_DEMO_FAULT_IDS))


def test_every_fault_declares_a_cause_and_a_validity_probe() -> None:
    for fault in FAULTS:
        assert fault.flag, fault.fault_id
        assert fault.expectation.expected_root_cause_category, fault.fault_id
        assert fault.expectation.required_keywords, fault.fault_id
        assert fault.expectation.validity_probe.check, fault.fault_id


def test_a_fault_with_no_validity_probe_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "cart-failure.yml"
    path.write_text(
        "fault_id: cart-failure\nflag: cartFailure\nvariant: 'on'\nservice: cart\n"
        "failure_mode: dependency_outage\nseverity: critical\ndifficulty: 2\n"
        "integrations: [kubernetes]\nexpected_symptom: [cart_error_rate_rising]\n"
        "expected_root_cause_category: dependency_failure\nrequired_keywords: [cart]\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="validity_probe"):
        load_fault(path)


# --- injection ----------------------------------------------------------------


def test_turning_a_fault_on_patches_the_demos_own_flag_document() -> None:
    runner = _flag_runner()
    faults = FlagdFaults(runner=runner, namespace="otel-demo")

    faults.set_variant("cartFailure", "on")

    assert runner.ran("patch", "configmap", OTEL_DEMO_FLAG_CONFIG)
    assert faults.variant_of("cartFailure") == "on"


def test_a_fault_naming_a_flag_the_demo_does_not_have_is_refused() -> None:
    faults = FlagdFaults(runner=_flag_runner(), namespace="otel-demo")

    with pytest.raises(FlagError, match="no flag called"):
        faults.set_variant("flagNobodyDeclared", "on")


# --- all five investigable, and every flag put back --------------------------


async def test_all_five_faults_run_end_to_end_and_leave_the_demo_as_it_found_it() -> None:
    runner = _flag_runner()
    faults = FlagdFaults(runner=runner, namespace="otel-demo")
    cluster = RecordedCluster(
        readings={
            probe: [sorted({symptom for fault in FAULTS for symptom in _symptoms(fault, probe)})]
            for probe in {fault.expectation.validity_probe.check for fault in FAULTS}
        }
    )
    investigator = DerivedInvestigator(
        expectations={fault.fault_id: expectation_of(fault) for fault in FAULTS},
        answer=correct_answer,
    )
    # The demo's alerts carry the fault under its own label, which is what the
    # derived investigator reads to know which expectation it is answering.
    investigator.expectations = {fault.fault_id: expectation_of(fault) for fault in FAULTS}

    report, outcomes = await run_faults(
        FAULTS,
        cluster=cluster,
        faults=faults,
        investigator=investigator,
        run_id="r1",
        sleep=lambda _: None,
        clock=_ticking(),
    )

    assert len(outcomes) == len(OTEL_DEMO_FAULT_IDS)
    for outcome in outcomes:
        assert outcome.ran, f"{outcome.fault_id}: {outcome.refused}"
        assert outcome.score is not None and outcome.score.scored, outcome.fault_id
    assert report.pass_rate == 1.0
    for fault in FAULTS:
        assert faults.variant_of(fault.flag) == fault.off_variant, fault.fault_id


async def test_a_flag_is_put_back_even_when_the_investigation_raises() -> None:
    runner = _flag_runner()
    faults = FlagdFaults(runner=runner, namespace="otel-demo")
    fault = FAULTS[0]

    class Exploding:
        async def investigate(self, alert: object, *, team: object, run_id: str = "") -> object:
            raise RuntimeError("the provider went away mid-investigation")

    from tests.e2e.otel_demo.runner import run_fault

    with pytest.raises(RuntimeError):
        await run_fault(
            fault,
            cluster=RecordedCluster(),
            faults=faults,
            investigator=Exploding(),  # type: ignore[arg-type]
            sleep=lambda _: None,
            clock=_ticking(),
        )

    assert faults.variant_of(fault.flag) == fault.off_variant


async def test_a_fault_that_did_not_propagate_is_reported_not_scored() -> None:
    fault = FAULTS[0]
    faults = FlagdFaults(runner=_flag_runner(), namespace="otel-demo")
    cluster = RecordedCluster(
        readings={fault.expectation.validity_probe.check: [["something_unrelated"]]}
    )
    investigator = DerivedInvestigator(
        expectations={fault.fault_id: expectation_of(fault)}, answer=wrong_answer
    )

    from tests.e2e.otel_demo.runner import run_fault

    outcome = await run_fault(
        fault,
        cluster=cluster,
        faults=faults,
        investigator=investigator,
        sleep=lambda _: None,
        clock=_ticking(),
    )

    assert outcome.score is not None
    assert outcome.score.experiment_failure
    assert not outcome.score.agent_failure


def _symptoms(fault: DemoFault, probe: str) -> tuple[str, ...]:
    """Return ``fault``'s declared symptoms when it uses ``probe``."""
    if fault.expectation.validity_probe.check != probe:
        return ()
    return fault.expectation.expected_symptom
