"""Exactly one lifecycle constructs an incident, and nothing else in the tree does.

A structural assertion rather than a behavioural one, because the property it
protects is structural. The plan's argument is that an ``Alert`` from webhooks
and an ``Incident`` from detectors means every downstream component handles two
cases and the second one is the one nobody tests. The defence against that is
not a test that both paths currently work — it is that there is only one
constructor, so a second path cannot be written by accident.

The check is a source scan rather than a runtime one on purpose. A second call
site would only fail a runtime check when somebody exercised it, and the whole
point is to fail on the commit that adds it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The one module allowed to *raise* an incident. Everything else asks it to.
LIFECYCLE: Final = REPO_ROOT / "platform" / "incidents" / "lifecycle.py"

#: The storage backends, which rebuild a stored incident rather than raising a
#: new one. Deserialisation is a different act from deciding something is wrong,
#: and a backend that could not construct the record it just read would have to
#: return a dictionary — which is the untyped seam the ports exist to remove.
#:
#: The demonstration seeder is here for exactly the same reason and no other. It
#: restores incidents that were *recorded* — identifiers, correlation keys,
#: subjects and all — from the committed dataset, so that a demonstration is the
#: deployment the capture describes rather than a fresh one that happens to
#: resemble it. Routing it through ``raise_incident`` would derive new
#: identifiers from the clock, which would break every reference the dataset's
#: other fixtures make to ``inc-0001`` and make two seeds of one dataset produce
#: two different deployments. It decides nothing is wrong; it reads what already
#: was.
REHYDRATORS: Final = (
    REPO_ROOT / "platform" / "persistence" / "postgres" / "repositories" / "incident_store.py",
    REPO_ROOT / "platform" / "startup" / "demo" / "seeder.py",
)

#: The packages a source scan covers: the shipped runtime. Tests construct
#: incidents freely — a contract suite has to be able to store one — and
#: ``tools/`` is not shipped.
PACKAGES: Final = (
    "config",
    "core",
    "platform",
    "integrations",
    "capabilities",
    "gateway",
    "surfaces",
)

#: Where the incident record is declared. The name alone is not enough: an
#: unrelated ``Incident`` — the capability scorer's input, for one — lives
#: elsewhere in the tree, and a check that counted it would be a check somebody
#: relaxes rather than reads.
INCIDENT_MODULES: Final = frozenset(
    {"platform.persistence.ports.incident_store", "platform.persistence.ports"}
)


def _sources() -> tuple[Path, ...]:
    """Return every shipped Python module."""
    return tuple(
        path
        for package in PACKAGES
        for path in sorted((REPO_ROOT / package).rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def _incident_names(tree: ast.Module) -> frozenset[str]:
    """Return the local names bound to *this* ``Incident``, if any."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in INCIDENT_MODULES:
            continue
        bound.update(alias.asname or alias.name for alias in node.names if alias.name == "Incident")
    return frozenset(bound)


def _constructs_an_incident(path: Path) -> bool:
    """Return whether ``path`` constructs the incident record."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = _incident_names(tree)
    if not names:
        return False
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names
        for node in ast.walk(tree)
    )


def test_exactly_one_module_constructs_an_incident() -> None:
    """A second constructor is a second lifecycle, whatever it is called."""
    constructing = [
        path for path in _sources() if path not in REHYDRATORS and _constructs_an_incident(path)
    ]

    assert [path.relative_to(REPO_ROOT).as_posix() for path in constructing] == [
        LIFECYCLE.relative_to(REPO_ROOT).as_posix()
    ], (
        "something other than the incident lifecycle constructs an Incident. Every "
        "origin — a detector, a webhook, a person — goes through "
        "IncidentLifecycle.raise_incident, because a second way to make one is a "
        "second lifecycle and the second one is the one nobody tests."
    )


def test_the_lifecycle_is_where_the_state_machine_lives() -> None:
    """The transitions are here too, so a caller cannot write a state directly."""
    source = LIFECYCLE.read_text(encoding="utf-8")

    for method in ("raise_incident", "transition", "self_close", "close", "suppress"):
        assert f"async def {method}" in source, f"the lifecycle no longer offers {method}"


def test_no_shipped_module_writes_an_incident_state_by_hand() -> None:
    """A caller that assigned a state would be a caller bypassing the timeline.

    ``replace(incident, state=...)`` outside the lifecycle would change an
    incident without recording why or who, which is the one thing every
    transition is required to carry.
    """
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _sources()
        if path != LIFECYCLE and "state=IncidentState." in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], (
        f"{offenders} assigns an incident state directly. Go through the lifecycle: a "
        "state change that skipped it would have no cause and no actor on the timeline."
    )
