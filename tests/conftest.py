"""Shared pytest configuration.

Puts the repository root at the head of ``sys.path`` so the seven first-party
packages import by their tier names (``config``, ``core``, ``platform``, …),
and binds the ``platform`` name to the first-party package rather than the
stdlib module pytest imported while bootstrapping.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _lead_sys_path_with_repo_root() -> None:
    """Move the repository root to the head of ``sys.path``.

    Merely being present is not enough. An editable install already puts the
    root on the path, but behind the stdlib — which would leave the stdlib
    ``platform`` module winning the name the first-party package must own.
    """
    root = str(REPO_ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)


def _bind_first_party_platform_package() -> None:
    """Make ``import platform`` reach the repository package during tests.

    ``platform/`` intentionally shadows the stdlib module, and it wins that
    name whenever the repository root leads ``sys.path`` — which is how every
    NinjaSRE process runs. pytest is the exception: it imports the stdlib
    ``platform`` while bootstrapping, long before this file executes, so the
    name is already bound by the time collection starts and
    ``platform.observability`` would be unimportable.

    Rebinding is safe. The package re-exports the stdlib module's entire public
    API, and anything that imported the stdlib earlier keeps its own reference
    to that module object.
    """
    cached = sys.modules.get("platform")
    if cached is not None and getattr(cached, "__path__", None) is not None:
        return

    sys.modules.pop("platform", None)
    importlib.invalidate_caches()
    importlib.import_module("platform")


_lead_sys_path_with_repo_root()
_bind_first_party_platform_package()
