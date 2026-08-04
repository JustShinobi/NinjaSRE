"""Exactly one module configures logging (FR-015).

A module that configures its own logging wins or loses depending on import
order. That produces a defect which is invisible in the test suite, invisible in
development, and appears only in the deployment whose entry point happens to
import things in the other sequence — usually while somebody is reading the logs
to work out why production is down.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

FIRST_PARTY_PACKAGES = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
)

#: The one module allowed to make these calls.
LOGGING_MODULE = REPO_ROOT / "platform" / "observability" / "logging.py"

#: Calls that configure logging process-wide.
CONFIGURING_CALLS = (
    ("structlog", "configure"),
    ("logging", "basicConfig"),
    ("logging", "dictConfig"),
)

pytestmark = pytest.mark.unit


def configuring_calls(source: str) -> list[tuple[str, str]]:
    """Return the process-wide logging configuration calls in ``source``."""
    tree = ast.parse(source)
    found: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue

        attribute = node.func
        target = attribute.value
        # structlog.configure(...) and logging.config.dictConfig(...) alike:
        # take the nearest qualifying name to the left of the call.
        if isinstance(target, ast.Attribute):
            module_name = target.attr
        elif isinstance(target, ast.Name):
            module_name = target.id
        else:
            continue

        if (module_name, attribute.attr) in CONFIGURING_CALLS:
            found.append((module_name, attribute.attr))

    return found


def first_party_modules() -> list[Path]:
    """Return every Python module in the seven first-party packages."""
    modules: list[Path] = []
    for package in FIRST_PARTY_PACKAGES:
        modules.extend(sorted((REPO_ROOT / package).rglob("*.py")))
    return [path for path in modules if "__pycache__" not in path.parts]


def test_the_logging_module_is_where_configuration_happens() -> None:
    """Guards the test itself: if this stops being true, the scan proves nothing."""
    calls = configuring_calls(LOGGING_MODULE.read_text(encoding="utf-8"))

    assert ("structlog", "configure") in calls
    assert ("logging", "basicConfig") in calls


def test_no_other_module_configures_logging() -> None:
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): calls
        for path in first_party_modules()
        if path != LOGGING_MODULE and (calls := configuring_calls(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}, (
        "logging is configured once, in platform/observability/logging.py; "
        f"these modules configure it too: {offenders}"
    )


def test_the_scan_would_catch_an_offender() -> None:
    """A negative test that never fires is a test that proves nothing."""
    assert configuring_calls("import structlog\n\nstructlog.configure()\n") == [
        ("structlog", "configure")
    ]
    assert configuring_calls("import logging\n\nlogging.basicConfig()\n") == [
        ("logging", "basicConfig")
    ]
    assert configuring_calls("from logging import config\n\nconfig.dictConfig({})\n") == []
