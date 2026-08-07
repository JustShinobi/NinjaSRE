"""Each thing the console gate claims, and the test that proves it.

Two of the gate's claims are about places no test can stand: the three-platform
workflow, and the wall-clock budget a contributor is willing to spend. Both are
still checkable — not by running them here, but by asserting that the workflow
declares them and that the tool which measures them reports the right verdict.

The rest of this module is the map: for each claim, the named test that proves
it, asserted to exist. A criterion whose proof was deleted or renamed fails here
rather than quietly ceasing to be covered — which is the failure mode a list of
claims in a document has and a list of claims in a test does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from config.constants.console import (
    CONSOLE_COLD_VERIFY_BUDGET_SECONDS,
    CONSOLE_WARM_VERIFY_BUDGET_SECONDS,
    NINJASRE_CONSOLE_TOOLCHAIN_ENV,
)
from tools.console_gate import REQUIRED
from tools.console_toolchain import REPO_ROOT, console_root
from tools.measure_verify import BUDGETS, EXIT_OVER_BUDGET, Measurement

pytestmark = pytest.mark.contract

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "verify.yml"

#: The platforms the workflow covers. Named here so that dropping one from the
#: workflow fails, rather than reducing what "all three platforms" means.
PLATFORMS = ("ubuntu-latest", "macos-latest", "windows-latest")


def workflow() -> dict[str, Any]:
    """Return the parsed quality-gate workflow."""
    loaded: Any = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def jobs() -> dict[str, Any]:
    """Return every job the workflow declares."""
    declared: Any = workflow()["jobs"]
    assert isinstance(declared, dict)
    return declared


@dataclass(frozen=True, slots=True)
class Claim:
    """One thing the gate claims, and where it is proven."""

    claim: str
    module: str
    test: str


#: Every claim this feature makes, against the test that holds it. The two the
#: workflow holds are asserted below rather than listed here, because their
#: proof is a job rather than a test.
CLAIMS = (
    Claim(
        "make verify runs both halves, and nothing sits outside it",
        "tests/contract/console/test_console_gate_configuration.py",
        "test_the_gate_runs_every_console_check",
    ),
    Claim(
        "a seeded failure fails its check and says where",
        "tests/contract/console/test_console_gate.py",
        "test_a_seeded_failure_fails_its_check_and_says_where",
    ),
    Claim(
        "and the same check passes once the fixture is gone",
        "tests/contract/console/test_console_gate.py",
        "test_the_same_check_passes_once_the_fixture_is_gone",
    ),
    Claim(
        "a seeded browser failure fails the gate",
        "tests/contract/console/test_console_gate.py",
        "test_a_seeded_end_to_end_failure_fails_the_gate",
    ),
    Claim(
        "a seeded pixel change fails the run and emits a diff",
        "tests/contract/console/test_console_visual_regression.py",
        "test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff",
    ),
    Claim(
        "a stale committed API client fails the build",
        "tests/contract/console/test_console_gate.py",
        "test_a_stale_committed_client_fails_the_build",
    ),
    Claim(
        "a stale lockfile fails rather than being rewritten",
        "tests/contract/console/test_console_gate.py",
        "test_a_stale_lockfile_fails_rather_than_being_rewritten",
    ),
    Claim(
        "nothing in the Python tree imports the console, and the reverse",
        "tests/unit/tools/test_check_console_boundary.py",
        "test_the_repository_keeps_the_boundary",
    ),
    Claim(
        "every design reference is registered, and every baseline was reviewed",
        "tests/contract/console/test_console_visual_coverage.py",
        "test_every_committed_reference_is_registered",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: claim.test)
def test_every_claim_has_the_test_it_names(claim: Claim) -> None:
    """The named test exists, in the named module."""
    module: Path = REPO_ROOT / claim.module
    assert module.is_file(), f"{claim.claim}: {claim.module} does not exist"
    assert f"def {claim.test}(" in module.read_text(encoding="utf-8"), (
        f"{claim.claim}: {claim.module} has no {claim.test}"
    )


def test_a_production_build_is_audited_for_third_party_requests() -> None:
    """The audit is a browser test, so it watches the built artefact rather than source."""
    audit: Path = console_root() / "tests" / "e2e" / "network.spec.ts"
    assert audit.is_file(), "there is no network audit"
    assert "page.on('request'" in audit.read_text(encoding="utf-8")


def test_the_gate_runs_on_every_platform_the_workflow_covers() -> None:
    """All three, and each one enforcing the console half rather than skipping it."""
    gate = jobs()["verify"]

    assert tuple(gate["strategy"]["matrix"]["os"]) == PLATFORMS
    assert gate["env"][NINJASRE_CONSOLE_TOOLCHAIN_ENV] == REQUIRED, (
        "the gate would let the console checks skip on the platforms it covers"
    )

    steps = "\n".join(str(step.get("run", "")) for step in gate["steps"])
    assert "make console-setup" in steps, "the gate does not provision the console toolchain"
    assert "make verify" in steps


def test_provisioning_is_cached_on_the_files_that_decide_what_it_is() -> None:
    """A run that changes no dependency restores; a run that changes one cannot."""
    caching = [
        step
        for step in jobs()["verify"]["steps"]
        if str(step.get("uses", "")).startswith("actions/cache@")
    ]
    assert caching, "the console toolchain is reinstalled on every run"

    key = str(caching[0]["with"]["key"])
    for deciding in ("toolchain.lock.json", ".node-version", "pnpm-lock.yaml", "package.json"):
        assert deciding in key, f"the cache key ignores {deciding}"
    assert "runner.os" in key and "runner.arch" in key, (
        "one cache across platforms would restore another platform's binaries"
    )


def test_the_visual_comparison_has_a_job_that_enforces_it() -> None:
    """`make verify` skips it where it cannot run; this is where it cannot skip."""
    visual = jobs()["console-visual"]

    assert visual["runs-on"] == "ubuntu-latest"
    assert visual["env"][NINJASRE_CONSOLE_TOOLCHAIN_ENV] == REQUIRED
    publishing = [
        step for step in visual["steps"] if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert publishing, "a failed comparison would report no image"
    assert publishing[0].get("if") == "failure()"


def test_the_compose_backed_suite_has_a_job() -> None:
    """The deployment's own definition, driven by the same browser suite."""
    compose = jobs()["console-e2e-compose"]
    steps = "\n".join(str(step.get("run", "")) for step in compose["steps"])
    assert "BACKING=compose" in steps


def test_both_budgets_are_measured_by_a_job() -> None:
    """A budget nobody measures is a wish."""
    steps = "\n".join(str(step.get("run", "")) for step in jobs()["console-budget"]["steps"])
    for profile in ("cold", "warm"):
        assert f"--profile {profile}" in steps, f"the {profile} budget is not measured"


def test_the_declared_budgets_are_the_ones_the_measurement_uses() -> None:
    """One place says how long the gate may take, and the tool reads it."""
    assert BUDGETS["cold"] == CONSOLE_COLD_VERIFY_BUDGET_SECONDS
    assert BUDGETS["warm"] == CONSOLE_WARM_VERIFY_BUDGET_SECONDS
    assert BUDGETS["warm"] < BUDGETS["cold"], "a warm gate that may be slower than a cold one"


def test_a_slow_gate_and_a_failed_gate_are_different_verdicts() -> None:
    """They are different problems for different people, so they report differently."""
    slow = Measurement("warm", seconds=BUDGETS["warm"] + 1, budget=BUDGETS["warm"], status=0)
    quick = Measurement("warm", seconds=1.0, budget=BUDGETS["warm"], status=0)
    broken = Measurement("warm", seconds=1.0, budget=BUDGETS["warm"], status=1)

    assert not slow.within_budget
    assert quick.within_budget
    assert broken.within_budget and broken.status != 0
    assert EXIT_OVER_BUDGET != 1, "a slow gate would be indistinguishable from a red one"


def test_the_measurement_reports_a_shape_a_workflow_can_publish() -> None:
    """One JSON object, with the number and the verdict beside it."""
    reported = Measurement("cold", seconds=12.34, budget=BUDGETS["cold"], status=0).as_json()

    assert re.search(r'"seconds":\s*12\.3', reported), reported
    for field in ("profile", "budget_seconds", "within_budget", "gate_passed"):
        assert f'"{field}"' in reported, reported
