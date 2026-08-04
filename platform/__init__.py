"""Tier 3 — cross-cutting platform services.

Owns persistence, the credential vault and proxy, the guardrail engine,
masking, the sandbox, memory stores, the knowledge graph, the scheduler,
notifications, identity, and observability. Carries no investigation logic.

This package deliberately shares its name with Python's stdlib ``platform``
module. The stdlib module's public API is re-exported here so that any caller doing
``import platform; platform.system()`` — including third-party dependencies
that never heard of NinjaSRE — keeps working, while first-party code can
import subpackages such as ``platform.observability``.
"""

from __future__ import annotations

import importlib.util
import os
import sysconfig
from pathlib import Path
from types import ModuleType

# Module name the genuine stdlib ``platform`` is loaded under. It must not
# collide with this package's own name, or the import machinery would resolve
# straight back here.
_STDLIB_MODULE_ALIAS = "_ninjasre_stdlib_platform"


def _candidate_stdlib_platform_paths() -> list[Path]:
    """Return the locations to probe for the genuine stdlib ``platform.py``."""
    candidates: list[Path] = []

    stdlib_dir = sysconfig.get_path("stdlib")
    if stdlib_dir:
        candidates.append(Path(stdlib_dir) / "platform.py")

    # Fallback: sit next to another stdlib module that is already imported.
    os_file = getattr(os, "__file__", None)
    if os_file:
        candidates.append(Path(os_file).resolve().parent / "platform.py")

    return candidates


def _load_stdlib_platform() -> ModuleType:
    """Load the genuine stdlib ``platform`` module from its source file.

    Because this package shadows the ``platform`` name, a plain ``import
    platform`` would resolve back to this module. The real one is therefore
    loaded directly from disk under a private alias.
    """
    candidates = _candidate_stdlib_platform_paths()
    for stdlib_path in candidates:
        if not stdlib_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(_STDLIB_MODULE_ALIAS, stdlib_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    checked = ", ".join(repr(str(path)) for path in candidates) or "<no candidate paths>"
    raise ImportError(f"Unable to load the stdlib platform module — checked: {checked}")


_stdlib_platform = _load_stdlib_platform()

for _name in dir(_stdlib_platform):
    if _name.startswith("__") and _name not in {"__all__", "__version__"}:
        continue
    globals()[_name] = getattr(_stdlib_platform, _name)

__all__ = tuple(_name for _name in dir(_stdlib_platform) if not _name.startswith("_"))
