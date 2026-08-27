"""`make test-fast SCOPE=...`: what an explicit scope selects, and when it refuses.

The automatic mode reads `git status` and maps each changed file onto the test
directory that mirrors it. `SCOPE=` bypassed that mapping entirely and handed
the string straight to pytest, so a *source* path — the thing a person reaches
for first, because it is the thing they just edited — collected nothing, hit
pytest's exit code 5, and was reported as a pass. A fast tier that runs nothing
and goes green is one people stop believing within a week, so both halves are
asserted here: an explicit scope goes through the same mapping, and a scope
that selects nothing is loud rather than silently green.

`RUN=true` replaces the pytest runner so these exercise the *selection* without
paying for the suite. What is under test is which paths the target chooses and
what status it leaves behind, neither of which depends on the tests passing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_test_fast(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `make test-fast` with the pytest runner stubbed out."""
    return subprocess.run(
        ["make", "test-fast", "RUN=true", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "scope",
    (
        "platform/memory",
        "platform/memory/",
    ),
)
def test_a_source_directory_scope_selects_the_tests_that_mirror_it(scope: str) -> None:
    """The path a person just edited is the path they name, so map it as the automatic mode does."""
    result = run_test_fast(f"SCOPE={scope}")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/unit/platform/memory" in result.stdout


def test_a_source_file_scope_selects_the_directory_that_mirrors_its_package() -> None:
    """A file selects its package's mirror, walking up until one exists — rule 1, unchanged."""
    result = run_test_fast("SCOPE=platform/memory/store.py")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/unit/platform/memory" in result.stdout


def test_a_scope_naming_a_test_path_is_passed_through_untouched() -> None:
    """Naming a suite directly stays the fastest way to run it, and must not be remapped."""
    result = run_test_fast("SCOPE=tests/unit/platform/memory")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/unit/platform/memory" in result.stdout


def test_a_scope_that_selects_nothing_fails_loudly() -> None:
    """Zero tests and exit 0 is the failure that teaches people to distrust the tier."""
    result = run_test_fast("SCOPE=docs/architecture.md")

    assert result.returncode != 0, result.stdout + result.stderr
    assert "docs/architecture.md" in result.stdout


def test_a_console_scope_is_refused_by_name_rather_than_run_empty() -> None:
    """The console has its own gate; silently running nothing would look like it passed."""
    result = run_test_fast("SCOPE=console/src/lib/api.ts")

    assert result.returncode != 0, result.stdout + result.stderr
    assert "console" in result.stdout
