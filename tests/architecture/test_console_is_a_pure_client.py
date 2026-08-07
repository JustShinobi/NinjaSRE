"""FR-030: the console renders and calls, and does nothing else.

The risk this guards is not that somebody writes a database query in a page — a
reviewer would catch that. It is the slow one: a screen needs a derived value,
computing it in TypeScript-ish Python is three lines, and eighteen months later
the console's idea of what a configuration resolves to has quietly diverged from
the deployment's. The plan names it as the first risk, and the mitigation it
names is a rule plus a dependency check, which is this.

Checked structurally rather than by review, because a review happens once and an
import check happens on every commit.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

CONSOLE = Path(__file__).resolve().parents[2] / "surfaces" / "console"

#: Packages the console must never reach into. ``gateway`` is the tier-1 peer
#: rule (``.importlinter`` enforces it too, and both are worth having: one names
#: the boundary, this one names the reason). The rest are the platform's
#: internals — a console that imported the persistence ports or the config
#: service would be a console that could stop asking the API.
FORBIDDEN_ROOTS = ("gateway", "capabilities", "integrations", "core")

#: The parts of ``platform`` the console may see, and why each is a vocabulary
#: rather than a behaviour.
ALLOWED_PLATFORM_MODULES = {
    # The permission catalogue: the names a principal's permissions are spelled
    # in. The console never decides what a role confers — it reads that from
    # ``GET /auth/me`` — but it must be able to say the names.
    "platform.identity.permissions",
    # The event-kind vocabulary the transcript renders. Rendering an event kind
    # the platform does not have would be a transcript that disagreed with the
    # trace.
    "platform.runs.events",
    # The masking token pattern, so a masked identifier can be shown as masked
    # rather than read as a hostname. Recognising a token is not restoring one.
    "platform.masking.mapping",
}

#: Names that would mean the console is doing the platform's job. Matched
#: against imported module paths, not against arbitrary text, so a docstring
#: mentioning "resolve" is not a violation.
FORBIDDEN_PLATFORM_AREAS = (
    "platform.persistence",
    "platform.config_service",
    "platform.credentials",
    "platform.approvals",
    "platform.memory",
    "platform.knowledge",
    "platform.guardrails",
    "platform.scheduler",
)


def _modules() -> Iterator[Path]:
    """Yield every Python module of the console."""
    return iter(sorted(CONSOLE.rglob("*.py")))


def _imports(source: Path) -> Iterator[str]:
    """Yield the dotted name of every module ``source`` imports."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


@pytest.mark.parametrize("source", _modules(), ids=lambda path: path.name)
def test_no_console_module_imports_a_package_below_tier_one(source: Path) -> None:
    offending = [
        imported for imported in _imports(source) if imported.split(".")[0] in FORBIDDEN_ROOTS
    ]

    assert offending == [], f"{source.name} imports {offending}"


@pytest.mark.parametrize("source", _modules(), ids=lambda path: path.name)
def test_the_console_reaches_only_the_vocabularies_it_declared(source: Path) -> None:
    """Every ``platform`` import is on the allow-list, with a reason written beside it."""
    offending = [
        imported
        for imported in _imports(source)
        if imported.split(".")[0] == "platform" and imported not in ALLOWED_PLATFORM_MODULES
    ]

    assert offending == [], (
        f"{source.name} imports {offending}. If the console genuinely needs it, add it to "
        f"ALLOWED_PLATFORM_MODULES with the reason it is a vocabulary rather than a behaviour."
    )


@pytest.mark.parametrize("source", _modules(), ids=lambda path: path.name)
def test_the_console_never_reaches_a_part_of_the_platform_that_decides_something(
    source: Path,
) -> None:
    offending = [
        imported
        for imported in _imports(source)
        if any(imported.startswith(area) for area in FORBIDDEN_PLATFORM_AREAS)
    ]

    assert offending == [], f"{source.name} imports {offending}, which the API is for"


def test_the_console_opens_no_database_connection_of_any_kind() -> None:
    """Article XI, checked at the only layer that could break it accidentally."""
    drivers = ("psycopg", "asyncpg", "sqlalchemy", "sqlite3", "pymongo", "redis")
    for source in _modules():
        for imported in _imports(source):
            root = imported.split(".")[0]
            assert root not in drivers, f"{source.name} imports {imported}"


def test_the_console_has_exactly_one_module_that_makes_a_request() -> None:
    """A second one would be a second place for a call to be made unlike the first."""
    http_modules = {
        source.name
        for source in _modules()
        for imported in _imports(source)
        if imported.split(".")[0] in {"urllib", "http", "httpx", "requests"}
    }

    assert http_modules == {"client.py"}


def test_every_console_module_is_actually_being_checked() -> None:
    """A guard that walked an empty directory would pass and mean nothing."""
    found = list(_modules())

    assert len(found) >= 10, f"only {len(found)} console modules were found"
    assert {"client.py", "app.py", "html.py"} <= {source.name for source in found}
