"""Where the fixture tree is, and where a raw capture must never be.

One module, because "which directory" is the question every other part of this
tooling asks first, and three answers to it is how a test writes into the
repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from config.constants.fixtures import (
    FIXTURE_ROOT_DIR_NAME,
    FIXTURE_SCENARIO_DIR_NAME,
    NINJASRE_CAPTURE_RAW_DIR_ENV,
    NINJASRE_FIXTURE_ROOT_ENV,
)
from config.constants.paths import REPO_ROOT, cache_dir


def fixture_root(root: Path | None = None) -> Path:
    """Return the fixture tree's root.

    ``root`` wins outright, then the environment, then the repository's own
    ``fixtures/``. The argument exists so a test can point the whole pipeline at
    a temporary tree without touching the environment, which is what makes the
    determinism and seeded-failure tests safe to run in parallel.
    """
    if root is not None:
        return root
    named = os.environ.get(NINJASRE_FIXTURE_ROOT_ENV, "").strip()
    if named:
        return Path(named).expanduser()
    return REPO_ROOT / FIXTURE_ROOT_DIR_NAME


def scenario_dir(scenario: str, root: Path | None = None) -> Path:
    """Return the directory holding one scenario's per-endpoint responses."""
    return fixture_root(root) / FIXTURE_SCENARIO_DIR_NAME / scenario


def raw_capture_dir() -> Path:
    """Return where a raw capture is written, which is never inside the repository.

    A raw capture carries hostnames, addresses, guest configuration and possibly
    cloud-init secrets. Defaulting it into the cache directory rather than the
    working tree means an operator who forgets to set anything still cannot
    commit one by accident.
    """
    named = os.environ.get(NINJASRE_CAPTURE_RAW_DIR_ENV, "").strip()
    if named:
        return Path(named).expanduser()
    return cache_dir() / "capture"


def is_inside_repository(path: Path) -> bool:
    """Return whether ``path`` resolves to somewhere inside the working tree."""
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


__all__ = [
    "fixture_root",
    "is_inside_repository",
    "raw_capture_dir",
    "scenario_dir",
]
