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
is not a `feat/NNN-slug` branch backed by a matching `specs/NNN-slug` directory.
It does not run `make verify` itself — the Makefile target it is wired to
(`make close-task`) depends on `verify`, so a red gate never reaches this script.

Usage::

    python tools/close_task_branch.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = REPO_ROOT / "specs"

BRANCH_PATTERN = re.compile(r"^feat/(\d{3}-[a-z0-9-]+)$")
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


def working_tree_is_clean() -> bool:
    """Return whether there is nothing staged, unstaged, or untracked."""
    return _git("status", "--porcelain") == ""


def spec_slugs() -> list[str]:
    """Return the `specs/` directory names in task order, oldest first."""
    return sorted(
        p.name for p in SPECS_DIR.iterdir() if p.is_dir() and SPEC_SLUG_PATTERN.match(p.name)
    )


def next_slug(slug: str, slugs: list[str]) -> str | None:
    """Return the spec that follows `slug` in task order, or None if it was the last."""
    index = slugs.index(slug)
    if index + 1 < len(slugs):
        return slugs[index + 1]
    return None


def close_task_branch(*, dry_run: bool = False) -> str:
    """Fast-forward master to the current task branch and branch the next task off it."""
    branch = current_branch()
    match = BRANCH_PATTERN.match(branch)
    if not match:
        raise CloseTaskError(f"{branch!r} is not a task branch (expected feat/NNN-slug)")
    slug = match.group(1)

    if not (SPECS_DIR / slug).is_dir():
        raise CloseTaskError(f"specs/{slug} does not exist — is this really the task branch?")

    if not working_tree_is_clean():
        raise CloseTaskError("working tree is dirty; commit or stash before closing the branch")

    upcoming = next_slug(slug, spec_slugs())
    next_branch = f"feat/{upcoming}" if upcoming else None

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
    args = parser.parse_args(argv)

    try:
        print(close_task_branch(dry_run=args.dry_run))
    except CloseTaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
