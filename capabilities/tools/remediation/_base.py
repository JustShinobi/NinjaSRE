"""The parts of the four components that are the same for all seven capabilities.

Each remediation capability provides a state reader, an applier, a rollback
generator, and a verifier. Six of the seven differ only in *which fields* they
read, write, restore, and compare — and writing seven copies of "read the
control plane, turn it into a snapshot" would produce seven chances for one of
them to handle an unreadable target differently from the rest.

So the shared shape lives here, parameterised by the fields, and each capability
package says only what is specific to it: which fields it is about, what the
desired state is, and what its rollback narrative reads like. What is
deliberately *not* shared is the narrative — "scale checkout-api in production
from 12 back to 4 replicas" is what an engineer at 3am can act on, and a
generic "restore the previous value" is not.

The one behaviour worth stating explicitly: an unreadable target produces
``StateSnapshot.unreadable`` rather than an empty snapshot, everywhere. An empty
snapshot fingerprints to a real value, would compare equal to another empty one,
and would let a rollback proceed against a target nobody could read.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from capabilities.tools.remediation import control_plane
from core.capability.result import CapabilityErrorClass, CapabilityResult
from platform.remediation.models import (
    WHOLE_TARGET,
    Divergence,
    RemediationAction,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
    SubTargetResult,
)
from platform.remediation.verification import divergences_between

#: What every remediation capability says when it is invoked directly rather
#: than through the gate. Named once so the seven refusals are one sentence and
#: an operator who sees it twice recognises it.
UNGATED_REFUSAL = (
    "A remediation capability is not callable directly. It runs through the "
    "remediation gate, which records the approval and the rollback plan before "
    "anything changes, and refuses when neither exists."
)

#: What they say when nobody has bound a control plane.
UNCONFIGURED_REFUSAL = (
    "No control plane is configured for this deployment, so there is nothing to "
    "change. An operator configures one before remediation is available."
)


def refuse(capability: str, *, detail: str = "") -> CapabilityResult:
    """Return the failure a directly-invoked remediation capability produces.

    ``PERMISSION_DENIED`` rather than ``APPROVAL_REQUIRED``: a model that called
    the tool function itself should not wait for a human, because nobody is
    being asked. The route it needs is the gate, and the message names it.
    """
    return CapabilityResult.failed(
        capability,
        CapabilityErrorClass.PERMISSION_DENIED,
        UNGATED_REFUSAL,
        detail=detail,
    )


@dataclass(frozen=True, slots=True)
class ControlPlaneReader:
    """Reads a target's state through whatever control plane is bound.

    ``fields`` narrows what a snapshot holds. Fingerprints are taken of the
    whole snapshot, so including everything a control plane happens to return
    would mark an unrelated annotation change as a conflict — and a conflict
    check that fires on noise is one reviewers learn to dismiss.
    """

    fields: tuple[str, ...]

    async def read(self, action: RemediationAction, *, at: datetime) -> StateSnapshot:
        """Return the target's observed state, or the snapshot that says it is unknown."""
        plane = control_plane.current()
        if plane is None:
            return StateSnapshot.unreadable(str(action.target), at=at)

        found = await plane.read(action)
        if found is None:
            return StateSnapshot.unreadable(str(action.target), at=at)

        return StateSnapshot(
            target=str(action.target),
            observed_at=at,
            values={name: found.values.get(name) for name in self.fields},
            sub_targets=found.sub_targets,
        )


@dataclass(frozen=True, slots=True)
class ControlPlaneApplier:
    """Sends the desired state to the control plane and reports what moved.

    ``desired_of`` is the capability's own knowledge, and it takes the prior
    state as well as the arguments: "scale to twice what it is" and "restore the
    limits it had" are both expressible, and neither is if the desired state can
    only be read out of the call.
    """

    desired_of: Callable[[RemediationAction, StateSnapshot], Mapping[str, Any]]

    async def apply(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        environment: Any,
    ) -> tuple[SubTargetResult, ...]:
        """Return one result per piece of the target that was attempted.

        ``environment`` names the sandbox this is running in and the proxy it
        reaches the control plane through. It is not used here — the bound
        control plane already goes through the proxy — and it is on the
        signature anyway, because a capability that could be applied without one
        is a capability that could be applied outside the sandbox.
        """
        del environment
        plane = control_plane.current()
        if plane is None:
            return ()
        return await plane.change(action, desired=self.desired_of(action, before), before=before)


@dataclass(frozen=True, slots=True)
class FieldVerifier:
    """Compares the fields the action intended to change against what came back.

    One-directional, against the intent rather than against the previous state.
    A change that moved the target somewhere neither party expected shows up
    here, where a before-and-after difference check would only notice that
    something happened.
    """

    intended_of: Callable[[RemediationAction, StateSnapshot], Mapping[str, Any]]

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return every field of the intent the resulting state does not agree with."""
        return divergences_between(self.intended_of(action, before), dict(after.values))


@dataclass(frozen=True, slots=True)
class RestoreGenerator:
    """Produces the "put the recorded values back" plan, named specifically.

    The family that covers five of the seven capabilities: a scale, a limit
    change, a flag toggle, a deploy, and a cordon are all undone by writing back
    what was there. What each of them is *called* is not shared, because the
    summary is what an engineer reads under pressure and "restore the previous
    value" tells them nothing about which value or where.
    """

    capability: str
    fields: tuple[str, ...]
    describe: Callable[[RemediationAction, StateSnapshot], str]
    #: Steps that name a sub-target are dropped when that piece was never
    #: touched. A restore acts on the target as a whole, so it names none.
    sub_target: str = WHOLE_TARGET

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the plan restoring the recorded values, or ``None`` when unknown.

        ``None`` for an unreadable target, deliberately. A plan that promised to
        restore values nobody read is a plan that would write nulls into
        production, and refusing the action is the correct outcome.
        """
        if not before.known:
            return None

        recorded = {name: before.values.get(name) for name in self.fields}
        return RollbackPlan(
            plan_id="",
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=self.describe(action, before),
            steps=(
                RollbackStep(
                    ordinal=1,
                    description=self.describe(action, before),
                    capability=self.capability,
                    arguments={**_target_arguments(action), **recorded},
                    sub_target=self.sub_target,
                ),
            ),
        )


def _target_arguments(action: RemediationAction) -> dict[str, Any]:
    """Return the arguments that name the thing a rollback step acts on."""
    return {
        "workload": action.target.identifier,
        "environment": action.target.environment,
    }


def steps_for(
    action: RemediationAction,
    *,
    capability: str,
    descriptions: Sequence[str],
    arguments: Mapping[str, Any] | None = None,
    sub_targets: Sequence[str] = (),
) -> tuple[RollbackStep, ...]:
    """Return an ordered set of steps, one per description.

    Used by the capabilities whose undo is a sequence rather than a single
    restore. Ordinals are assigned here so no capability has to remember that
    the executor sorts by them.
    """
    shared = {**_target_arguments(action), **dict(arguments or {})}
    return tuple(
        RollbackStep(
            ordinal=position,
            description=description,
            capability=capability,
            arguments=shared,
            sub_target=sub_targets[position - 1] if position <= len(sub_targets) else WHOLE_TARGET,
        )
        for position, description in enumerate(descriptions, start=1)
    )


@dataclass(frozen=True, slots=True)
class Unavailable:
    """The reader a capability uses when its control plane cannot answer at all.

    Exists so a deployment with no control plane produces the same shape as one
    whose control plane is down, rather than an import error at the moment
    somebody registers the components.
    """

    fields: tuple[str, ...] = field(default_factory=tuple)

    async def read(self, action: RemediationAction, *, at: datetime) -> StateSnapshot:
        """Return the snapshot that says the target could not be read."""
        return StateSnapshot.unreadable(str(action.target), at=at)


__all__ = [
    "UNCONFIGURED_REFUSAL",
    "UNGATED_REFUSAL",
    "ControlPlaneApplier",
    "ControlPlaneReader",
    "FieldVerifier",
    "RestoreGenerator",
    "Unavailable",
    "refuse",
    "steps_for",
]
