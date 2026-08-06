"""The claim the whole feature exists to support: nothing writes without permission.

Asserted through every entry point rather than through the one the gate happens
to be wired to, because "no unapproved write" is only true if it is true of the
way somebody else calls it. Three entry points exist and all three are here: the
capability function a model could call, the executor a console button reaches,
and the gate the loop drives.

The assertion in each case is the same and is made against the control plane
rather than against a return value: nothing was applied. A test that checked for
a refusal would still pass if the refusal arrived after the change.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from capabilities.tools.remediation import COMPONENTS
from capabilities.tools.remediation import control_plane as plane_binding
from core.capability.result import CapabilityErrorClass
from platform.approvals.policy import SecurityPolicy
from platform.remediation.autonomy.kill_switch import KillSwitch
from platform.remediation.execution import RemediationExecutor
from platform.remediation.gating import GatingPolicy, RemediationGate, RunContext
from platform.remediation.models import RemediationAction
from platform.remediation.request import RequestBuilder
from platform.remediation.rollback.generator import PlanFactory

#: A fixed instant, so an expiry assertion is arithmetic rather than a race.
EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def test_no_shipped_write_capability_acts_when_called_directly() -> None:
    """Every remediation tool refuses its own invocation and names the gate.

    The entry point a model has. A capability function that performed its action
    would be one that ran with no approval, no plan, and no sandbox, because
    none of those live in the function.
    """
    from capabilities.registry.catalogue import build_registry, reset_registry_cache

    reset_registry_cache()
    registry = build_registry()
    remediation = [
        found
        for found in registry.tools.values()
        if found.metadata.domain == "remediation"
        and found.metadata.side_effect_level.needs_approval
    ]

    assert len(remediation) == len(COMPONENTS), (
        "every shipped remediation capability must be a write that declares four components"
    )

    for found in remediation:
        arguments = {
            name: _placeholder(schema)
            for name, schema in found.input_schema.get("properties", {}).items()
        }
        result = _invoke(found, arguments)
        assert not result.succeeded, f"{found.name} performed its action when called directly"
        assert result.error is not None
        assert result.error.classification is CapabilityErrorClass.PERMISSION_DENIED, found.name


async def test_the_gate_refuses_when_nobody_approved_and_nothing_is_allow_listed(
    registry,
    plans: PlanFactory,
    executor: RemediationExecutor,
    plane,
    an_action,
    clock,
) -> None:
    """A gated action with no approver and no entry does not reach the target.

    The default path, and the one every other refusal is a variation on. There
    is no allow-list, no decision waiter, and therefore no way for the action to
    become permitted — and the assertion is that the control plane saw nothing.
    """
    gate = RemediationGate(
        requests=RequestBuilder(registry=registry, plans=plans, clock=clock),
        executor=executor,
        run=RunContext(requester="ada", team_node_id="team-payments"),
        clock=clock,
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied, "a write reached the target with nobody having approved it"
    assert "waiting on a human approval" in outcome.reason


async def test_the_executor_refuses_while_the_kill_switch_is_engaged(
    registry,
    isolation,
    verification,
    plane,
    an_action,
    clock,
) -> None:
    """The console-button entry point is gated by the same checks as the loop's.

    An executor reached directly — from a surface, a replayed run, an operator's
    CLI — must not be a way around the controls. It holds the kill switch itself
    for exactly that reason.
    """
    switch = KillSwitch()
    switch.engage(engaged_by="grace", reason="cluster is unstable", at=clock())
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        kill_switch=switch,
        clock=clock,
    )

    from platform.remediation.errors import KillSwitchEngaged

    action = an_action()
    before = await _before(registry, action, clock)
    plan = PlanFactory(registry=registry, clock=clock, identifiers=lambda: "plan-x").generate(
        action, before=before
    )

    with pytest.raises(KillSwitchEngaged):
        await executor.execute(action, plan=plan, before=before)

    assert not plane.was_applied
    assert isolation.entered == 0, "a sandbox was provisioned for a refused action"


def test_the_default_policy_gates_every_write_level() -> None:
    """An organisation that configured nothing still gates every write.

    Silence is not permission. A deployment that has not named its gated levels
    has not decided to run production writes unattended — it has not decided
    anything, and the safe reading of that is the strict one.
    """
    policy = GatingPolicy.of_policy(SecurityPolicy())

    from core.capability.metadata import SideEffectLevel

    assert not policy.gates(SideEffectLevel.READ)
    assert not policy.gates(SideEffectLevel.READ_SENSITIVE)
    assert policy.gates(SideEffectLevel.WRITE_REVERSIBLE)
    assert policy.gates(SideEffectLevel.WRITE_IRREVERSIBLE)
    assert policy.gates(SideEffectLevel.DESTRUCTIVE)


def test_an_organisation_cannot_ungate_a_write_by_leaving_it_off_its_list() -> None:
    """A policy naming only one level still gates the others.

    Article III is not an organisational preference. A policy may add levels to
    what it gates and may not remove a write from it, which is why the check is
    the policy's list *or* the scale rather than the list alone.
    """
    from config.constants.security import SIDE_EFFECT_READ_SENSITIVE
    from core.capability.metadata import SideEffectLevel

    policy = GatingPolicy.of_policy(
        SecurityPolicy(require_approval_for_side_effect_levels=(SIDE_EFFECT_READ_SENSITIVE,))
    )

    assert policy.gates(SideEffectLevel.READ_SENSITIVE), "the organisation asked for this one"
    assert policy.gates(SideEffectLevel.DESTRUCTIVE), "and cannot give this one up"


async def test_an_unbound_control_plane_leaves_every_capability_unreadable(an_action) -> None:
    """With nothing bound, a shipped reader reports the target as unknown.

    Not empty. An empty snapshot fingerprints to a real value and would compare
    equal to another empty one, which is how a rollback proceeds against a
    target nobody could read.
    """
    from capabilities.tools.remediation.scale_workload.read_state import reader

    previous = plane_binding.bind(None)
    try:
        snapshot = await reader.read(an_action(), at=EPOCH)
    finally:
        plane_binding.restore(previous)

    assert not snapshot.known
    assert snapshot.fingerprint != ""


# --- helpers -----------------------------------------------------------------


def _placeholder(schema: object) -> object:
    """Return a value of the right shape for one declared argument."""
    kind = schema.get("type") if isinstance(schema, dict) else "string"
    return {"integer": 1, "number": 1.0, "boolean": True}.get(str(kind), "x")


def _invoke(found, arguments):
    """Return the result of calling a tool body from a synchronous test."""
    import asyncio

    return asyncio.run(found.invoke(arguments))


async def _before(registry, action: RemediationAction, clock):
    """Return the target's state before the action, through its own reader."""
    return await registry.get(action.capability).reader.read(action, at=clock())
