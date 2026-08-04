"""Fail the build if a telemetry package reaches the runtime dependency tree.

NinjaSRE contains no first-party telemetry, analytics, crash reporting, or usage
tracking that transmits off-host, and no component phones home. The target
operator runs regulated infrastructure, where opt-out telemetry is a procurement
blocker rather than a growth lever.

A *direct* dependency on one of these would be caught in review. The one that
would not is transitive — pulled in three levels down by a library whose
changelog nobody read. This walks the resolved tree in ``uv.lock``, so both are
the same failure.

Two things are deliberately out of scope:

- **Development dependencies.** They never ship.
- **Optional extras.** An extra is opted into by an operator who decided to; it
  is not what a default install runs.

Usage::

    python tools/check_dependencies.py

Exits 0 when the tree is clean, 1 when it is not.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = REPO_ROOT / "uv.lock"
PROJECT_NAME = "ninjasre"

#: Packages that transmit usage data off-host. Names are stored normalised, so
#: a lock file spelling one ``sentry_sdk`` matches the entry for ``sentry-sdk``.
#:
#: OpenTelemetry is deliberately absent: it is opt-in and points at a collector
#: the operator configures, which is the opposite of a library that decides on
#: its own to phone home.
TELEMETRY_DENY_LIST: frozenset[str] = frozenset(
    {
        "amplitude-analytics",
        "analytics-python",
        "mixpanel",
        "posthog",
        "segment-analytics-python",
        "sentry-sdk",
    }
)

_NAME_SEPARATORS = re.compile(r"[-_.]+")


def normalise_package_name(name: str) -> str:
    """Return the PEP 503 normalised form of a distribution name."""
    return _NAME_SEPARATORS.sub("-", name).lower()


def _dependency_names(entry: dict[str, Any]) -> list[str]:
    """Return the runtime dependency names declared by one lock entry.

    Only the ``dependencies`` table. ``optional-dependencies`` and
    ``dev-dependencies`` live under their own keys and are not runtime.
    """
    dependencies = entry.get("dependencies", [])
    if not isinstance(dependencies, list):
        return []

    names: list[str] = []
    for dependency in dependencies:
        if isinstance(dependency, dict):
            name = dependency.get("name")
            if isinstance(name, str):
                names.append(normalise_package_name(name))
    return names


def runtime_dependency_names(lock_text: str, root_package: str) -> set[str]:
    """Return every package the runtime tree reaches from ``root_package``.

    Raises:
        ValueError: ``root_package`` is not in the lock file. Passing silently
            on an unreadable lock would defeat the check entirely.
    """
    document = tomllib.loads(lock_text)
    entries = {
        normalise_package_name(str(entry["name"])): entry
        for entry in document.get("package", [])
        if isinstance(entry, dict) and "name" in entry
    }

    root = normalise_package_name(root_package)
    if root not in entries:
        raise ValueError(f"{root_package!r} is not present in the lock file")

    reached: set[str] = set()
    queue = deque(_dependency_names(entries[root]))

    while queue:
        name = queue.popleft()
        if name in reached:
            continue
        reached.add(name)
        entry = entries.get(name)
        if entry is not None:
            queue.extend(_dependency_names(entry))

    reached.discard(root)
    return reached


def find_banned_dependencies(lock_text: str, root_package: str) -> list[str]:
    """Return every deny-listed package in the runtime tree, sorted."""
    reached = runtime_dependency_names(lock_text, root_package)
    return sorted(reached & TELEMETRY_DENY_LIST)


def main(argv: Sequence[str] | None = None) -> int:
    """Check the resolved runtime tree against the telemetry deny-list."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--lock",
        type=Path,
        default=LOCK_FILE,
        help="path to uv.lock (default: the repository's)",
    )
    arguments = parser.parse_args(argv)

    if not arguments.lock.is_file():
        print(f"{arguments.lock} is missing; run `make install` first.", file=sys.stderr)
        return 1

    banned = find_banned_dependencies(arguments.lock.read_text(encoding="utf-8"), PROJECT_NAME)

    if not banned:
        return 0

    print(
        f"{len(banned)} telemetry package(s) in the runtime dependency tree:",
        file=sys.stderr,
    )
    for name in banned:
        print(f"  {name}", file=sys.stderr)
    print(
        "\nNothing may leave the operator's host without an explicit decision "
        "(Constitution Article X). Move the dependency behind an optional extra, "
        "or drop the library that pulls it in.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
