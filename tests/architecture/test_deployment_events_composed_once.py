"""Exactly one root composes the deployment event channel — nowhere else does.

The plan's argument for FR-005/FR-007: `DeploymentEventBroker` is built once,
handed to the run broker that taps it and to the persistence gateway decorator
that taps incidents and decisions, and nothing else in the shipped tree may
construct a second one — a second broker is a second channel a console screen
could be reading from without the composition root's own guarantee that the
one it drains from is the one every write path publishes to.

A source scan rather than a runtime one, for the reason
`test_one_incident_lifecycle.py` gives: a second construction only fails a
runtime check when something exercises it, and the point is to fail on the
commit that adds it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The one module allowed to construct the broker: the deployment's real boot
#: sequence, not a route, not a fixture, not a decorator that merely receives one.
ROOT: Final = REPO_ROOT / "gateway" / "http" / "asgi.py"

#: Where `DeploymentEventBroker` is declared.
DECLARING_MODULE: Final = "platform.runs.deployment"

#: The packages a source scan covers: the shipped runtime, not `tools/`, which
#: is not shipped, and not the test tree, which constructs one freely to drive
#: a fixture.
PACKAGES: Final = (
    "config",
    "core",
    "platform",
    "integrations",
    "capabilities",
    "gateway",
    "surfaces",
)


def _sources() -> tuple[Path, ...]:
    """Return every shipped Python module."""
    return tuple(
        path
        for package in PACKAGES
        for path in sorted((REPO_ROOT / package).rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def _broker_names(tree: ast.Module) -> frozenset[str]:
    """Return the local names bound to *this* ``DeploymentEventBroker``, if any."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != DECLARING_MODULE:
            continue
        bound.update(
            alias.asname or alias.name
            for alias in node.names
            if alias.name == "DeploymentEventBroker"
        )
    return frozenset(bound)


def _constructs_the_broker(path: Path) -> bool:
    """Return whether ``path`` constructs ``DeploymentEventBroker`` itself.

    Declaring the class (``platform/runs/deployment.py`` itself, where every
    name in ``_broker_names`` would be empty because nothing there imports it
    from itself) is not a construction site by this definition, which is
    correct: the class body is not a call to it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = _broker_names(tree)
    if not names:
        return False
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names
        for node in ast.walk(tree)
    )


def test_exactly_one_module_constructs_the_deployment_event_broker() -> None:
    """A second construction is a second channel, whatever it is called."""
    constructing = [path for path in _sources() if _constructs_the_broker(path)]

    assert [path.relative_to(REPO_ROOT).as_posix() for path in constructing] == [
        ROOT.relative_to(REPO_ROOT).as_posix()
    ], (
        "something other than gateway/http/asgi.py constructs a DeploymentEventBroker. "
        "One channel, built once at the root, is the whole of FR-004's guarantee that "
        "a reconnecting client's epoch means the same process every time — a second "
        "broker is a second epoch sequence nothing keeps in step with the first."
    )


def test_the_root_taps_both_the_run_broker_and_the_persistence_gateway() -> None:
    """The two write-path taps FR-005 and FR-007 name are both composed here.

    A source assertion rather than a behavioural one: the behaviour is already
    covered by `tests/unit/platform/runs/test_deployment_run_tap.py` and
    `tests/unit/platform/persistence/test_deployment_taps.py`. What only a read
    of this file can show is that the *composed* deployment actually wires the
    tapped classes in, rather than the plain ones the tests exercise directly.
    """
    source = ROOT.read_text(encoding="utf-8")
    assert "DeploymentPublishingRunEventBroker(" in source, (
        "the root no longer builds a tapped run broker — a plain RunEventBroker here "
        "would mean run events reach the per-run stream and never the deployment one"
    )
    assert "with_deployment_events(" in source, (
        "the root no longer decorates the persistence gateway — incident and decision "
        "writes would stop publishing to the deployment channel with nothing failing "
        "loudly to say so"
    )


def test_gateway_state_is_handed_the_same_broker_the_route_drains() -> None:
    """`GatewayState.deployment_events` is the object the tap publishes to, not a second one."""
    source = ROOT.read_text(encoding="utf-8")
    assert "deployment_events=deployment_events" in source, (
        "GatewayState is not receiving the same deployment_events instance the run "
        "broker and the persistence decorator were built with — two instances here "
        "would mean the route serves a broker nothing ever publishes to"
    )
