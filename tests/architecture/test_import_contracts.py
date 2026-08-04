"""Each boundary violation is caught, and named, by its own contract.

The six fixture trees under ``fixtures/`` each carry all seven first-party
package names and exactly one illegal import. Running the repository's real
``.importlinter`` against a tree therefore isolates one rule: the contract that
owns that boundary must break, and no other forbidden or independence contract
may fire.

``layers`` breaks on every fixture as well, and that is the point — it encodes
the downward-only ordering, so any violation of a specific rule is also a
violation of the ordering. Asserting the exact broken set keeps both facts
honest: the specific contract is what names the boundary (SC-004), and the
ordering contract is what proves the tiers are ordered at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from contract_config import CONTRACT_CONFIG, LAYERS_CONTRACT, declared_contracts

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RUNNER = Path(__file__).resolve().parent / "run_contracts.py"

pytestmark = pytest.mark.architecture


@dataclass(frozen=True)
class ViolationFixture:
    """A module tree that breaks exactly one boundary rule."""

    directory: str
    contract: str
    violation: str

    @property
    def path(self) -> Path:
        return FIXTURES_DIR / self.directory


VIOLATION_FIXTURES = (
    ViolationFixture("config_is_a_leaf", "config-is-a-leaf", "config imports core"),
    ViolationFixture(
        "integrations_below_capabilities",
        "integrations-below-capabilities",
        "integrations imports capabilities",
    ),
    ViolationFixture(
        "integrations_below_tier1",
        "integrations-below-tier1",
        "integrations imports gateway",
    ),
    ViolationFixture(
        "capabilities_below_tier1",
        "capabilities-below-tier1",
        "capabilities imports surfaces",
    ),
    ViolationFixture(
        "tier1_peers_independent",
        "tier1-peers-independent",
        "surfaces imports gateway",
    ),
    ViolationFixture("tier3_below_tier2", "tier3-below-tier2", "core imports integrations"),
)

COMPLIANT_FIXTURE = FIXTURES_DIR / "tier3_siblings_cross_import"


def run_contracts(package_root: Path) -> subprocess.CompletedProcess[str]:
    """Check the repository's contracts against an isolated module tree."""
    environment = {
        **os.environ,
        # Keep the report plain so the assertions read a stable stdout. The wide
        # console matters: the report is rendered by rich, which wraps at 80
        # columns off a terminal and would split a contract name away from its
        # KEPT/BROKEN verdict.
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "200",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, str(RUNNER), str(package_root), str(CONTRACT_CONFIG)],
        # The tree under test must be the working directory: lint_imports puts
        # os.getcwd() at the head of sys.path, so running from the repository
        # root would graph the real packages instead of the fixture.
        cwd=package_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=environment,
    )


def broken_contracts(report: str) -> set[str]:
    """Return the identifiers of every contract the report marks as broken.

    Each contract is named ``<identifier>: <sentence>`` so the report names the
    rule that was violated rather than a section number.
    """
    identifiers = declared_contracts()
    broken: set[str] = set()

    for line in report.splitlines():
        stripped = line.strip()
        if not stripped.endswith("BROKEN"):
            continue
        for identifier in identifiers:
            if stripped.startswith(f"{identifier}:"):
                broken.add(identifier)
                break

    return broken


def test_every_fixture_targets_a_distinct_contract() -> None:
    """The six fixtures name six different rules (SC-004)."""
    targeted = [fixture.contract for fixture in VIOLATION_FIXTURES]

    assert len(targeted) == 6
    assert len(set(targeted)) == len(targeted)


def test_every_declared_contract_except_layers_has_a_fixture() -> None:
    """No boundary rule ships without a test that proves it fires."""
    targeted = {fixture.contract for fixture in VIOLATION_FIXTURES}
    declared = set(declared_contracts()) - {LAYERS_CONTRACT}

    assert declared == targeted, "a contract exists with no fixture proving it breaks"


@pytest.mark.parametrize("fixture", VIOLATION_FIXTURES, ids=lambda fixture: fixture.contract)
def test_fixture_breaks_only_its_own_contract(fixture: ViolationFixture) -> None:
    """The violation is rejected, and the report names the rule it broke."""
    result = run_contracts(fixture.path)

    assert result.returncode == 1, (
        f"{fixture.violation} was accepted\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert broken_contracts(result.stdout) == {fixture.contract, LAYERS_CONTRACT}, (
        f"{fixture.violation} did not break exactly "
        f"{fixture.contract} and {LAYERS_CONTRACT}\nstdout:\n{result.stdout}"
    )


def test_tier3_siblings_may_cross_import() -> None:
    """``core`` and ``platform`` are siblings; the dependency may run either way."""
    result = run_contracts(COMPLIANT_FIXTURE)

    assert result.returncode == 0, (
        f"a legal core <-> platform cross-import was rejected\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert broken_contracts(result.stdout) == set()
