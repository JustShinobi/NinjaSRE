"""Exactly one path writes the alert's receipt onto an incident's timeline.

``IncidentLifecycle.record_alert_received`` is the write itself; this is
about how many places call it. Two call sites reachable from production is
the defect this feature closes — not a call site disabled by configuration,
one that no longer exists.
"""

from __future__ import annotations

import ast

import pytest

from config.constants.paths import REPO_ROOT

pytestmark = pytest.mark.architecture

#: First-party source, walked for call sites. Not ``tests/`` — a fixture or a
#: characterisation test is allowed to call the method it is characterising.
_PRODUCTION_PACKAGES = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
)

#: The module that declares the method. A call from inside its own definition
#: is not a second writer; it is the writer.
_DECLARING_MODULE = "platform/incidents/lifecycle.py"


def _call_sites(method: str) -> list[str]:
    """Return ``package/module.py:line`` for every ``self.<method>(`` or
    ``<name>.<method>(`` call in first-party source, the declaring module excepted."""
    found: list[str] = []
    for package in _PRODUCTION_PACKAGES:
        for path in (REPO_ROOT / package).rglob("*.py"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative == _DECLARING_MODULE:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == method
                ):
                    found.append(f"{relative}:{node.lineno}")
    return found


def test_exactly_one_production_call_site_writes_the_alert_receipt() -> None:
    sites = _call_sites("record_alert_received")

    assert len(sites) == 1, (
        "record_alert_received is called from more than one place reachable from "
        f"production: {sites}. Exactly one writer may exist."
    )


def test_the_one_writer_is_start_investigation() -> None:
    sites = _call_sites("record_alert_received")

    assert sites, "no production call site writes the alert receipt at all"
    assert sites[0].startswith("gateway/http/orchestration.py"), (
        f"the single writer moved to an unexpected place: {sites[0]}"
    )
