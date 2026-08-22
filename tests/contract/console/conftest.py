"""Protection for the two suites here that deliberately damage the checkout.

Two modules in this directory break the working tree on purpose, to prove a
gate notices. `test_console_gate` splices broken source files where a check
will find them; `test_console_visual_regression` writes a blank image over a
committed baseline. Both repair themselves in a `finally` — and a `finally` is
exactly what a killed process does not run.

That has bitten this repository six times. Every time the residue read as a
defect somebody had introduced rather than as a test that did not get to
finish, and every time it cost somebody the walk from a confusing symptom back
to this cause. One of the spliced files, an unattributed component under
`src/lib/`, was carried for a whole feature as a mystery nobody could account
for: nobody wrote it, a test did.

Two mechanisms, because there are two ways to arrive at the same mess.

**A sweep**, for the run that died. Residue from yesterday must not be today's
failure, and every spliced destination is a file only these tests create, so
removing one is unambiguous rather than clever.

**A lock**, for the two runs at once. Two processes seeding and unseeding the
same paths interleave into a state neither one's cleanup is correct for, which
is how a suite reports a failure that describes nothing that is wrong.

What is deliberately *not* here is repair of the baseline image. It is a
committed file, and a fixture that quietly reverts committed files is a fixture
that eventually eats work somebody meant to keep. A dirty baseline directory
stops the run and says so instead.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from config.constants.console import CONSOLE_BASELINE_DIR_NAME, CONSOLE_VISUAL_DIR_NAME
from tools.console_toolchain import REPO_ROOT, console_root

#: Every path the seeding tests write into the console, relative to its root.
#:
#: Held here rather than derived from the tests that use them, so the sweep does
#: not depend on importing a test module — and `test_console_gate` asserts its
#: own list against this one, so the two cannot drift apart in silence.
SEEDED_DESTINATIONS: Final = (
    "src/lib/crooked.ts",
    "src/lib/reaching.ts",
    "src/lib/broken.tsx",
    "src/lib/swatch.tsx",
    "src/shell/untranslated.tsx",
    "tests/unit/seeded.test.ts",
    "tests/e2e/seeded.spec.ts",
)

#: The xdist group every test in this directory is put into.
#:
#: The lock below is per process, and an xdist worker is a process with its own
#: session. Spread across workers, every worker after the first would find the
#: lock taken and call ``pytest.exit`` — the suite failing over contention it
#: created itself. One group means one worker holds the checkout, which is the
#: same guarantee a serial run gave.
#:
#: It costs less than it sounds. These suites are the longest in the repository,
#: so they set the floor either way; what parallelism buys is everything *else*
#: finishing alongside them rather than after them.
CONSOLE_TREE_GROUP: Final = "console-tree"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Pin every test collected from this directory to one worker."""
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.xdist_group(CONSOLE_TREE_GROUP))


#: Where the lock lives. Inside the toolchain directory because that is already
#: ignored, so the lock never shows up as a change somebody has to explain.
_LOCK: Final = console_root() / ".toolchain" / "tree-writing-suite.lock"

#: How long a lock may sit before it is assumed to belong to a dead process.
#:
#: The suites it guards take minutes, not hours. A lock older than this is the
#: same failure it exists to prevent — a run that died holding something — so
#: waiting on it forever would only trade one stuck state for another.
_LOCK_STALE_SECONDS: Final = 3600


def _sweep() -> list[str]:
    """Remove any spliced file left behind, returning what was removed."""
    removed = []
    for relative in SEEDED_DESTINATIONS:
        path = console_root() / relative
        if path.exists():
            path.unlink()
            removed.append(relative)
    return removed


def _take_lock() -> bool:
    """Return whether this process took the lock, clearing a stale one first."""
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    if _LOCK.exists() and time.time() - _LOCK.stat().st_mtime > _LOCK_STALE_SECONDS:
        _LOCK.unlink(missing_ok=True)
    try:
        handle = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(handle, "w", encoding="utf-8") as writing:
        writing.write(f"{os.getpid()}\n")
    return True


@pytest.fixture(scope="session", autouse=True)
def guard_the_tree() -> Iterator[None]:
    """Hold the lock for the session, and sweep residue at both ends."""
    if not _take_lock():
        holder = _LOCK.read_text(encoding="utf-8").strip() or "unknown"
        pytest.exit(
            f"another run is already writing into the console checkout "
            f"(process {holder}, {_LOCK}). These suites splice broken files into "
            f"the tree and remove them again; two runs at once interleave into a "
            f"state neither one's cleanup repairs. Wait for it, or delete the lock "
            f"if that process is gone.",
            returncode=1,
        )
    swept = _sweep()
    if swept:
        # Reported rather than silently repaired: residue means a run died, and
        # that is worth knowing even though this one can carry on.
        print(f"\nswept residue from an interrupted run: {', '.join(swept)}")
    try:
        yield
    finally:
        _sweep()
        _LOCK.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def baselines_start_clean(guard_the_tree: None) -> None:
    """Refuse to start when a committed baseline is already modified.

    The visual suite overwrites one and restores it, so a modified baseline at
    the start of a run is either residue from a killed one or somebody's
    unfinished acceptance. Both are reasons to stop: the first makes the run
    report a difference nobody introduced, and the second would have this suite
    trample work in progress.
    """
    baselines = Path(CONSOLE_VISUAL_DIR_NAME) / CONSOLE_BASELINE_DIR_NAME
    finished = subprocess.run(
        ["git", "status", "--porcelain", "--", str(console_root().name / baselines)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = [line for line in finished.stdout.splitlines() if line.strip()]
    if dirty:
        pytest.exit(
            "a committed visual baseline is modified before the suite started:\n"
            + "\n".join(dirty)
            + "\n\nIf a previous run was killed, `git checkout -- ` the paths above. "
            "If this is an acceptance in progress, commit or stash it first — this "
            "suite overwrites a baseline and restores it, and it must not restore "
            "over your work.",
            returncode=1,
        )
