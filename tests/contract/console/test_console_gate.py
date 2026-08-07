"""Each console check, shown a file it must reject.

The first wave declined a TypeScript console because it would have been
invisible to ``make verify`` — lint, types, tests and all — while the gate went
green. That reasoning was only worth overturning by removing the premise, and
the premise is only removed if each check *actually fails*. A configuration that
declares a rule and a runner that never reaches the file are indistinguishable
from the outside, and both leave the gate green.

So every check here is handed a file from ``console/fixtures/`` that breaks it,
run for real, and required to fail and to say where. The fixtures live outside
the lint, format and type configurations, so they are only ever checked in the
place a test deliberately put them.

These tests need the console toolchain. On a machine that has not provisioned
it they skip with a name; CI sets ``NINJASRE_CONSOLE_TOOLCHAIN=required`` and
then the skip is a failure, which is what makes the coverage real where it is
enforced.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from config.constants.console import NINJASRE_CONSOLE_TOOLCHAIN_ENV
from tools.console_gate import REQUIRED
from tools.console_toolchain import REPO_ROOT, console_root, is_provisioned

pytestmark = [pytest.mark.contract, pytest.mark.console]

FIXTURES = console_root() / "fixtures"


def _toolchain_required() -> bool:
    return os.environ.get(NINJASRE_CONSOLE_TOOLCHAIN_ENV, "").strip().lower() == REQUIRED


needs_toolchain = pytest.mark.skipif(
    not is_provisioned() and not _toolchain_required(),
    reason=(
        "the console toolchain is not provisioned; run `make console-setup`, or set "
        f"{NINJASRE_CONSOLE_TOOLCHAIN_ENV}={REQUIRED} to make this a failure"
    ),
)


@dataclass(frozen=True, slots=True)
class SeededFailure:
    """One broken file, where it has to be put, and which check must reject it."""

    fixture: str
    destination: str
    check: str
    #: A fragment the failure has to contain, so "it failed" is not enough — it
    #: has to have failed *about this*.
    names: str


SEEDED = (
    SeededFailure("format-violation.ts", "src/lib/crooked.ts", "format-check", "crooked.ts"),
    SeededFailure("lint-violation.ts", "src/lib/reaching.ts", "lint", "reaching.ts"),
    SeededFailure("type-error.tsx", "src/lib/broken.tsx", "typecheck", "broken.tsx"),
    # A colour written out, a length off the spacing scale, and a duration
    # written out. The design system is a set of closed sets, and a closed set
    # nothing enforces is a suggestion.
    SeededFailure("design-literal-violation.tsx", "src/lib/swatch.tsx", "lint", "swatch.tsx"),
    SeededFailure("failing.test.ts", "tests/unit/seeded.test.ts", "test", "seeded.test.ts"),
)


@contextmanager
def spliced(seeded: SeededFailure) -> Iterator[Path]:
    """Put the broken file where the check will look, and take it away afterwards."""
    source = FIXTURES / seeded.fixture
    destination = console_root() / seeded.destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        yield destination
    finally:
        destination.unlink(missing_ok=True)


def run_gate(check: str) -> subprocess.CompletedProcess[str]:
    """Run one console check exactly as the Makefile does."""
    return subprocess.run(
        [sys.executable, "-m", "tools.console_gate", check],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, NINJASRE_CONSOLE_TOOLCHAIN_ENV: REQUIRED},
    )


def test_every_seeded_fixture_exists() -> None:
    """The fixtures are committed, so this suite cannot pass by finding nothing."""
    for seeded in SEEDED:
        assert (FIXTURES / seeded.fixture).is_file(), seeded.fixture
    assert (FIXTURES / "failing.spec.ts").is_file()


@needs_toolchain
@pytest.mark.parametrize("seeded", SEEDED, ids=lambda seeded: seeded.check)
def test_a_seeded_failure_fails_its_check_and_says_where(seeded: SeededFailure) -> None:
    """The check rejects the file, names it, and names itself."""
    with spliced(seeded):
        finished = run_gate(seeded.check)

    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, f"{seeded.check} passed on {seeded.fixture}:\n{output}"
    assert seeded.names in output, f"{seeded.check} did not name {seeded.names}:\n{output}"
    assert seeded.check in output, f"the failure did not name the check:\n{output}"


@needs_toolchain
@pytest.mark.parametrize("seeded", SEEDED, ids=lambda seeded: seeded.check)
def test_the_same_check_passes_once_the_fixture_is_gone(seeded: SeededFailure) -> None:
    """The other half: the check is not simply always red."""
    finished = run_gate(seeded.check)
    assert finished.returncode == 0, finished.stdout + finished.stderr


@needs_toolchain
def test_a_seeded_end_to_end_failure_fails_the_gate() -> None:
    """A browser test that fails takes the gate with it."""
    seeded = SeededFailure("failing.spec.ts", "tests/e2e/seeded.spec.ts", "e2e", "seeded.spec.ts")
    with spliced(seeded):
        finished = run_gate("e2e")

    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, f"the browser suite passed on a failing test:\n{output}"
    assert "seeded.spec.ts" in output, output


@needs_toolchain
def test_a_stale_lockfile_fails_rather_than_being_rewritten() -> None:
    """A manifest the lockfile does not describe is a change somebody has to make."""
    manifest = console_root() / "package.json"
    original = manifest.read_text(encoding="utf-8")
    drifted = original.replace(
        '"devDependencies": {',
        '"devDependencies": {\n    "left-pad": "1.3.0",',
        1,
    )
    assert drifted != original, "the manifest did not have the shape this test edits"

    manifest.write_text(drifted, encoding="utf-8")
    try:
        finished = run_gate("lockfile")
    finally:
        manifest.write_text(original, encoding="utf-8")

    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, f"a drifted lockfile was accepted:\n{output}"
    assert "lockfile" in output.lower(), output


@needs_toolchain
def test_a_stale_committed_client_fails_the_build() -> None:
    """The generated client is compared against a fresh generation, not trusted."""
    from config.constants.console import CONSOLE_GENERATED_CLIENT_PATH

    client = console_root() / CONSOLE_GENERATED_CLIENT_PATH
    original = client.read_text(encoding="utf-8")
    client.write_text(
        original.replace("export interface paths {", "export interface paths {\n  // stale", 1),
        encoding="utf-8",
    )
    try:
        finished = run_gate("client-check")
    finally:
        client.write_text(original, encoding="utf-8")

    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, f"a stale client was accepted:\n{output}"
    assert CONSOLE_GENERATED_CLIENT_PATH in output, output
    assert client.read_text(encoding="utf-8") == original, (
        "the drift check rewrote the committed client instead of reporting it"
    )
