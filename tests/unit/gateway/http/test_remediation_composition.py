"""Composing the desk that turns a proposed write into a stored approval.

Everything a remediation needs has existed for some time: the gate, the request
builder, the plan factory, the executor, the component registry, the approval
routes and the three tables. Nothing built any of it. A sweep for a constructed
gate returned tests, contract tests and the mock data plane — which is to say
the mechanism was written and the deployment did not have it.

So these tests are about the wiring rather than about the parts. Three
properties, and each one has a way it would be silently wrong:

**The desk exists at all in a deployment that can carry a write.** The failure
this replaces is the field that stayed ``None`` on every deployment there has
ever been.

**One desk, two consumers.** The loop reaches it to propose and the approval
route reaches it to carry a decision out. Two constructions would be two
executors, two kill-switch readings and two audit trails.

**A deployment that cannot remediate composes nothing and names what is
missing.** Silent degradation here reads exactly like a policy that decided not
to act, and those are opposite facts.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from gateway.http.remediation import compose_remediation, unmet_for_remediation
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.remediation.models import RemediationAction, StateSnapshot, SubTargetResult

pytestmark = pytest.mark.unit

ORG = "acme"

#: Where a sandbox reaches the credential proxy. Any absolute address: nothing
#: in these tests sends a packet, and the policy type refuses to describe a
#: sandbox with nowhere to authenticate through.
PROXY = "http://127.0.0.1:8787"


class _Plane:
    """A control plane that answers, so the deployment can carry a write."""

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=("one",))

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        del action, desired, before
        return ()


@pytest.fixture
def plane() -> Any:
    """Bind a control plane for the test and put back whatever was there."""
    previous = control_plane.bind(_Plane())
    yield
    control_plane.restore(previous)


@pytest.fixture
def unbound() -> Any:
    """Unbind the control plane, which is what a fresh deployment has."""
    previous = control_plane.bind(None)
    yield
    control_plane.restore(previous)


def _state() -> GatewayState:
    """Return the gateway state a composition root would hand the composer."""
    store = FakePersistence()
    return GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=ReActInvestigationRunner(llm=None, registry=Registry()),  # type: ignore[arg-type]
    )


async def test_a_deployment_that_can_remediate_gets_a_desk(plane: None) -> None:
    state = _state()

    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)

    assert desk is not None, (
        "nothing composed a remediation desk for a deployment with a control plane, "
        "a sandbox profile and registered components. Every write this deployment "
        "declares would refuse for want of a caller."
    )
    assert state.remediation is desk


async def test_the_desk_carries_the_writes_this_deployment_has_components_for(
    plane: None,
) -> None:
    state = _state()

    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)

    assert desk is not None
    assert desk.handles("scale_workload")
    assert not desk.handles("prometheus_metric_statistics"), (
        "the desk claims a read as something it carries. What it holds is the set of "
        "capabilities with four registered components, and nothing else."
    )


async def test_the_runner_and_the_approval_route_read_one_desk(plane: None) -> None:
    """Two consumers, one object — never two constructions that could disagree."""
    state = _state()

    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)

    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)
    assert runner.remediation is desk, (
        "the runner holds a different desk from the one the approval route reads. "
        "Two desks are two executors, two kill-switch readings and two audit trails."
    )


async def test_a_deployment_with_no_control_plane_composes_nothing(unbound: None) -> None:
    state = _state()

    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)

    assert desk is None
    assert state.remediation is None
    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)
    assert runner.remediation is None


async def test_what_is_missing_is_named_rather_than_left_to_be_inferred(
    unbound: None,
) -> None:
    """ "It did not compose" and "it decided not to act" must not look alike."""
    state = _state()

    unmet = unmet_for_remediation(state)

    assert unmet, "a deployment with no control plane reported nothing missing"
    assert any("control plane" in reason for reason in unmet), (
        f"the missing pieces were reported as {unmet}, which does not name the "
        f"control plane an operator would have to configure."
    )


async def test_a_deployment_that_can_remediate_reports_nothing_missing(plane: None) -> None:
    assert unmet_for_remediation(_state()) == ()


# -- the order in the composition root ----------------------------------------


#: The function in the async composition root that this feature's call joins.
ROOT_FUNCTION = "lifespan"


def _calls_in_lifespan() -> list[str]:
    """Return the plain function calls the async composition root makes, in order.

    Walked from the syntax tree rather than matched as text, so it survives a
    rename of a local variable, a reformatting, or a line being wrapped.
    """
    from gateway.http import lifespan as module

    tree = ast.parse(inspect.getsource(module))
    root = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == ROOT_FUNCTION
    )
    called = [
        (node.lineno, node.func.id)
        for node in ast.walk(root)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    return [name for _, name in sorted(called)]


def test_the_async_composition_root_composes_the_desk() -> None:
    assert "compose_remediation" in _calls_in_lifespan(), (
        "the async composition root never calls compose_remediation. A desk nothing "
        "builds is a desk no deployment has."
    )


def test_the_desk_is_composed_after_the_runner_is_rebuilt() -> None:
    """Composing first would hand the desk to the runner that was thrown away.

    ``recompose_investigator`` replaces the runner once the operator's model
    choice and the vault's keys have been read. A desk installed before that
    would be installed on the object that is about to be discarded, and the
    loop that actually runs would have none.
    """
    order = _calls_in_lifespan()

    assert "recompose_investigator" in order
    assert order.index("compose_remediation") > order.index("recompose_investigator"), (
        "the remediation desk is composed before the runner is rebuilt, so it is "
        "attached to the runner that is then thrown away."
    )


def test_the_desk_is_composed_after_the_bindings_its_executor_reaches_through() -> None:
    """The executor reaches a vendor through the proxy that these two bind."""
    order = _calls_in_lifespan()

    for earlier in ("compose_integration_access", "compose_provider_credentials"):
        assert order.index("compose_remediation") > order.index(earlier), (
            f"the remediation desk is composed before {earlier}, so it would reach a "
            f"vendor through a binding that does not exist yet."
        )
