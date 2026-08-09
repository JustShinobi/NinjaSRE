"""Turning one declaration into the four components the executor calls.

Thirteen hypervisor writes differ in which fields they read, what state they
intend, and what their undo reads like. They do not differ in *how* those four
things are assembled, and writing thirteen copies of the assembly would produce
thirteen chances for one of them to handle an unreadable target differently from
the rest.

So the assembly is here, parameterised by the declaration, and each action says
only what is specific to it. Two behaviours are worth stating because they are
the ones a copy would get wrong.

**An unreadable target produces no plan.** A plan promising to put back values
nobody read is a plan that would write nulls into a hypervisor, and refusing the
action is the correct outcome. The generator returns ``None`` and the gate does
the refusing.

**A capability that declares no undo returns nothing, rather than inventing one.**
Deleting a snapshot has no reversal. Saying so sends the request down the waiver
path — refuse unless an operator explicitly accepts it, and audit the acceptance
— which is the only honest route for an action whose effect is permanent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from capabilities.tools.remediation._base import ControlPlaneApplier, ControlPlaneReader
from capabilities.tools.remediation.proxmox.declaration import ProxmoxRemediation
from core.capability.metadata import RollbackPlan as DeclaredRollbackPlan
from platform.remediation.components import OutcomeVerifier, RemediationComponents
from platform.remediation.models import (
    Divergence,
    RemediationAction,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
)
from platform.remediation.verification import divergences_between

#: What ``{restored}`` renders as when nothing has been read yet — the metadata
#: planner's case, which produces a plan from call arguments alone.
UNREAD_VALUES = "the values recorded immediately before the action"


def _context(
    action: RemediationAction, before: StateSnapshot, fields: tuple[str, ...]
) -> dict[str, str]:
    """Return what a rollback template may name: the target, and what was recorded."""
    recorded = ", ".join(f"{name}={before.values.get(name)!r}" for name in fields)
    return {"target": action.target.identifier, "restored": recorded or UNREAD_VALUES}


def _step_arguments(action: RemediationAction, recorded: Mapping[str, Any]) -> dict[str, Any]:
    """Return the arguments a rollback step is replayed with.

    The guest's identity comes from the action's own arguments rather than from
    its target string: a hypervisor addresses a guest by node, kind and number,
    and reconstructing those from ``name@environment`` would be a naming
    convention standing in for three facts.
    """
    identity = {
        name: action.arguments.get(name)
        for name in ("node", "vmid", "kind", "datastore", "sid", "job_id")
        if name in action.arguments
    }
    return {**identity, **dict(recorded)}


@dataclass(frozen=True, slots=True)
class DeclaredRestore:
    """Produces the plan that puts the recorded values back, named specifically."""

    declaration: ProxmoxRemediation

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the plan reversing ``action``, or ``None`` when there is none to derive."""
        rollback = self.declaration.rollback
        if not rollback.derivable or not before.known:
            return None

        fields = self.declaration.fields
        context = _context(action, before, fields)
        recorded = {name: before.values.get(name) for name in fields}
        return RollbackPlan(
            plan_id="",
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=rollback.summary.format(**context),
            reversible=rollback.reversible,
            steps=tuple(
                RollbackStep(
                    ordinal=position,
                    description=step.format(**context),
                    capability=rollback.performed_by or self.declaration.capability,
                    arguments=_step_arguments(action, recorded),
                )
                for position, step in enumerate(rollback.steps, start=1)
            ),
        )


@dataclass(frozen=True, slots=True)
class NoDerivablePlan:
    """Says plainly that this action has no undo, and never invents one."""

    declaration: ProxmoxRemediation

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return ``None``: what this action does cannot be reversed."""
        del action, before
        return None


@dataclass(frozen=True, slots=True)
class DeclaredPlanner:
    """The declaration's rollback, rendered from call arguments for the catalogue.

    What the tool metadata carries, as opposed to what the executor stores. It is
    the same sentences from the same declaration, so an operator reading the
    catalogue and an operator reading a stored plan are reading one decision.
    """

    declaration: ProxmoxRemediation

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing an invocation made with ``arguments``."""
        rollback = self.declaration.rollback
        target = str(arguments.get("vmid", arguments.get("sid", "the target")))
        context = {"target": target, "restored": UNREAD_VALUES}
        if not rollback.derivable:
            return DeclaredRollbackPlan(
                summary=f"No rollback: {rollback.absent_because}",
                steps=(
                    "Confirm what the action removed, from the task log it left behind.",
                    "Recover from a copy held somewhere this system did not write to.",
                ),
                reversible=False,
            )
        return DeclaredRollbackPlan(
            summary=rollback.summary.format(**context),
            steps=tuple(step.format(**context) for step in rollback.steps),
            reversible=rollback.reversible,
        )


@dataclass(frozen=True, slots=True)
class IntentVerifier:
    """Compares what came back against what the action intended, field by field."""

    declaration: ProxmoxRemediation

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return every field of the intent the resulting state does not agree with."""
        intended = self.declaration.intent_of(action, before)
        return divergences_between(intended, dict(after.values))


@dataclass(frozen=True, slots=True)
class StartedVerifier:
    """A guest started when it is running *and* its own agent answers.

    Reaching ``running`` is Proxmox's opinion of the container or the virtual
    machine, taken from outside it. A guest whose kernel booted and whose
    services did not is ``running`` and is not up, and the guest agent is the
    only reading available from inside — so where one is declared, it decides.

    ``agent_responds`` is ``None`` for a guest that declares no agent, and that
    is not a failure: it is the honest statement that nothing inside the guest
    is reachable to ask. A verifier that treated it as one would report every
    container as broken.
    """

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return a divergence unless the guest is running and its agent answered."""
        del action, before
        status = str(after.values.get("status", ""))
        if status != "running":
            return (
                Divergence(
                    field_name="status",
                    intended="running",
                    actual=status or "unreadable",
                ),
            )
        if after.values.get("agent_responds") is False:
            return (
                Divergence(
                    field_name="agent_responds",
                    intended="the guest agent answers, because the guest declares one",
                    actual="it did not answer, so the guest booted and did not come up",
                ),
            )
        return ()


@dataclass(frozen=True, slots=True)
class RestartedVerifier:
    """A guest restarted when it is running *and younger than it was*.

    The comparison the field check cannot make. A reboot ends where it started —
    running — so a verifier comparing status to ``running`` passes on a reboot
    that never happened. Uptime is the only reading that distinguishes them, and
    it is the whole reason this capability's snapshot carries one.
    """

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return a divergence unless the guest came back and its uptime reset."""
        del action
        status = str(after.values.get("status", ""))
        if status != "running":
            return (
                Divergence(
                    field_name="status",
                    intended="running",
                    actual=status or "unreadable",
                ),
            )
        was = _seconds(before.values.get("uptime"))
        now = _seconds(after.values.get("uptime"))
        if now >= was:
            return (
                Divergence(
                    field_name="uptime",
                    intended=f"lower than the {was}s it had before the reboot",
                    actual=f"{now}s, so the guest never restarted",
                ),
            )
        return ()


def _seconds(raw: Any) -> int:
    """Return ``raw`` as a whole number of seconds, treating anything else as zero."""
    return int(raw) if isinstance(raw, int | float) else 0


def components_for(
    declaration: ProxmoxRemediation,
    *,
    verifier: OutcomeVerifier | None = None,
) -> RemediationComponents:
    """Return the four components and the verification declaration for one write.

    ``verifier`` overrides the field-by-field comparison for the one action whose
    intended state is not expressible as a set of values — a reboot, which ends
    in the state it started from.
    """
    return RemediationComponents(
        capability=declaration.capability,
        reader=ControlPlaneReader(fields=declaration.fields),
        applier=ControlPlaneApplier(desired_of=declaration.intent_of),
        generator=(
            DeclaredRestore(declaration=declaration)
            if declaration.rollback.derivable
            else NoDerivablePlan(declaration=declaration)
        ),
        verifier=verifier if verifier is not None else IntentVerifier(declaration=declaration),
        verification=declaration.verification,
    )


__all__ = [
    "UNREAD_VALUES",
    "DeclaredPlanner",
    "DeclaredRestore",
    "IntentVerifier",
    "NoDerivablePlan",
    "RestartedVerifier",
    "StartedVerifier",
    "components_for",
]
