"""Close a finished spec-task branch and open the next one (SDD workflow helper).

Each task in `specs/` gets its own branch. Left to its own devices, a new branch
gets created off the *previous* task's branch instead of off `master` — that is
the path of least resistance, and it means `master` never advances and every
later branch carries the full weight of every earlier one.

This closes the loop the other way: fast-forward `master` to the finished task
branch (only if the history is a straight line — anything else means `master`
moved or the branch was never rebased onto it, and this refuses to guess), then
branch the next spec directly off the now-current `master`.

It refuses to touch a dirty working tree and refuses to run from anything that
is not a `feat/[wave-]NNN-slug` branch backed by a matching spec directory. It does not
run `make verify` itself — the Makefile target it is wired to (`make close-task`)
depends on `verify`, so a red gate never reaches this script.

The directory holding the specs is resolvable rather than fixed. Work proceeds in
waves, and a later wave lives in its own directory beside the first; hard-coding
one of them would mean either editing this file per wave or maintaining a second
copy of the branch/slug contract, and the second copy is the one that drifts.
Set ``NINJASRE_SPECS_DIR`` (a name, or a path relative to the repository root) or
pass ``--specs-dir``; it defaults to ``specs``.

Usage::

    python tools/close_task_branch.py [--dry-run] [--specs-dir specs_v2]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The default spec directory and the environment variable that overrides it —
# declared in the constants tier like every other environment-variable name, so
# this script, ``make close-task`` and the unattended runner all agree without
# any of them passing the value to the others.
from config.constants.workflow import (  # noqa: E402
    DEFAULT_SPECS_DIRNAME,
    SPECS_DIR_ENV,
)


def resolve_specs_dir(name: str | None = None) -> Path:
    """Return the spec directory to work against.

    Precedence: the explicit argument, then ``NINJASRE_SPECS_DIR``, then
    ``specs``. An absolute path is honoured as given; anything else is taken
    relative to the repository root, so ``specs_v2`` and ``./specs_v2`` mean the
    same thing whatever the caller's working directory is.
    """
    raw = name or os.environ.get(SPECS_DIR_ENV) or DEFAULT_SPECS_DIRNAME
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


#: The default, kept as a module constant because importers rely on it. Callers
#: that need a different wave call ``resolve_specs_dir`` instead.
SPECS_DIR = resolve_specs_dir()

BRANCH_PATTERN = re.compile(r"^feat/(?:(?P<wave>[a-z0-9][a-z0-9-]*)-)?(?P<slug>\d{3}-[a-z0-9-]+)$")
SPEC_SLUG_PATTERN = re.compile(r"^\d{3}-")


class CloseTaskError(Exception):
    """The branch cannot be closed as asked."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CloseTaskError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def current_branch() -> str:
    """Return the checked-out branch name."""
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def parse_task_branch(branch: str) -> tuple[str, str]:
    """Return the optional wave prefix and spec slug encoded in ``branch``."""
    match = BRANCH_PATTERN.match(branch)
    if match is None:
        raise CloseTaskError(f"{branch!r} is not a task branch (expected feat/[wave-]NNN-slug)")
    wave = match.group("wave")
    return (f"{wave}-" if wave else "", match.group("slug"))


def working_tree_is_clean() -> bool:
    """Return whether there is nothing staged, unstaged, or untracked."""
    return _git("status", "--porcelain") == ""


def spec_slugs(specs_dir: Path | None = None) -> list[str]:
    """Return the spec directory names in task order, oldest first."""
    root = specs_dir or SPECS_DIR
    return sorted(p.name for p in root.iterdir() if p.is_dir() and SPEC_SLUG_PATTERN.match(p.name))


def next_slug(slug: str, slugs: list[str]) -> str | None:
    """Return the spec that follows `slug` in task order, or None if it was the last."""
    index = slugs.index(slug)
    if index + 1 < len(slugs):
        return slugs[index + 1]
    return None


def close_task_branch(*, dry_run: bool = False, specs_dir: Path | None = None) -> str:
    """Fast-forward master to the current task branch and branch the next task off it."""
    root = specs_dir or SPECS_DIR
    branch = current_branch()
    wave_prefix, slug = parse_task_branch(branch)

    if not (root / slug).is_dir():
        rel = root.relative_to(REPO_ROOT) if root.is_relative_to(REPO_ROOT) else root
        raise CloseTaskError(f"{rel}/{slug} does not exist — is this really the task branch?")

    if not working_tree_is_clean():
        raise CloseTaskError("working tree is dirty; commit or stash before closing the branch")

    upcoming = next_slug(slug, spec_slugs(root))
    next_branch = f"feat/{wave_prefix}{upcoming}" if upcoming else None

    if dry_run:
        summary = f"would fast-forward master to {branch}"
        if next_branch:
            summary += f", then branch {next_branch} off master"
        else:
            summary += f" ({slug} is the last planned spec — no next branch)"
        return summary

    _git("checkout", "master")
    try:
        _git("merge", "--ff-only", branch)
    except CloseTaskError as exc:
        _git("checkout", branch)
        raise CloseTaskError(
            f"master did not fast-forward to {branch}: {exc}. "
            f"Rebase {branch} onto master and try again."
        ) from exc

    if next_branch:
        _git("checkout", "-b", next_branch, "master")
        return f"master now at {branch}; created {next_branch} off master"
    return f"master now at {branch}; {slug} was the last planned spec, no branch created"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dry-run", action="store_true", help="print the plan without acting")
    parser.add_argument(
        "--specs-dir",
        default=None,
        metavar="DIR",
        help=(
            f"spec directory to read, relative to the repository root "
            f"(default: ${SPECS_DIR_ENV} or {DEFAULT_SPECS_DIRNAME})"
        ),
    )
    args = parser.parse_args(argv)

    specs_dir = resolve_specs_dir(args.specs_dir)
    if not specs_dir.is_dir():
        print(f"error: {specs_dir} is not a directory", file=sys.stderr)
        return 1

    try:
        print(close_task_branch(dry_run=args.dry_run, specs_dir=specs_dir))
    except CloseTaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
