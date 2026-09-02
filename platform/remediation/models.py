"""The six values a production change is made of, and what each one is for.

An approval mechanism already exists, and this package does not build a second
one. What it builds is the shape of the thing being approved: a proposed change
to a live system, the state it was proposed against, the steps that would undo
it, and — afterwards — what actually happened per sub-target and whether the
result matched the intent.

Three of the shapes here are worth the paragraph they cost.

**``StateSnapshot`` carries a fingerprint and a "known" flag.** The fingerprint
is what makes an approval mean something: it is taken of the target's state when
the action is proposed and compared again before the plan is applied, so a
rollback written against twelve replicas cannot land on a workload somebody has
since taken to two. ``known`` is separate from "empty" because "we could not read
the target" and "the target holds nothing" lead to opposite decisions, and only
one of them is safe to act on.

**``RollbackPlan`` knows which sub-target each step covers.** An action that
restarts three of five pods must produce a plan covering three, not five. Storing
the association per step is what makes ``scoped_to`` a filter rather than a
guess, and a plan that over-reached would be a second unreviewed change carried
out under the authority of the first.

**``ExecutionRecord`` records per sub-target, always.** "It worked" and "it
worked for three of five" are different outcomes, and a record that flattened
them would leave the partial case looking like a success in every report that
reads it afterwards.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from config.constants.security import (
    REMEDIATION_PAYLOAD_ARGUMENTS,
    REMEDIATION_PAYLOAD_BLAST_RADIUS,
    REMEDIATION_PAYLOAD_CAPABILITY,
    REMEDIATION_PAYLOAD_ENVIRONMENT,
    REMEDIATION_PAYLOAD_EVIDENCE,
    REMEDIATION_PAYLOAD_ROLLBACK,
    REMEDIATION_PAYLOAD_STEPS,
    REMEDIATION_PAYLOAD_WAIVER,
    REMEDIATION_ROLLBACK_WINDOW_SECONDS,
)
from core.capability.metadata import SideEffectLevel
from platform.approvals.models import fingerprint_of
from platform.persistence.ports.approval_store import RollbackPlan as StoredRollbackPlan
from platform.persistence.ports.approval_store import RollbackStep as StoredRollbackStep

#: How a step says it covers the target as a whole rather than one piece of it.
#: A literal empty string would read as "the sub-target nobody filled in", and
#: the difference decides whether a partial-success filter keeps the step.
WHOLE_TARGET = ""


class ExecutionOutcome(StrEnum):
    """How far an execution got.

    ``PARTIAL`` is a first-class outcome rather than a failed success. Three of
    five pods restarted is the ordinary result of acting on a live system, and
    it needs a rollback plan covering three — which is a different obligation
    from either of its neighbours.

    ``UNCHANGED`` is a first-class outcome too, and for the same reason:
    a target the control plane read as already in the desired state was
    attempted and answered, not skipped and not refused. Collapsing it into
    ``FAILED`` would report an action that worked — in the sense that its
    intent already held — as one that went wrong, which is the same
    "pretended execution" the success direction is guarded against, just
    read backwards.
    """

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    REFUSED = "refused"

    @property
    def changed_anything(self) -> bool:
        """Return whether anything about the target was altered."""
        return self in (ExecutionOutcome.SUCCEEDED, ExecutionOutcome.PARTIAL)


@dataclass(frozen=True, slots=True)
class RemediationTarget:
    """What is being changed, where it runs, and who owns it.

    ``environment`` is its own field rather than part of the identifier because
    two different mechanisms read it: the allow-list refuses production unless
    an entry names it, and the approval request shows it to the reviewer above
    everything else. Parsing it back out of a string would make both depend on a
    naming convention nobody enforces.
    """

    identifier: str
    environment: str = ""
    node_id: str | None = None
    kind: str = "workload"

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("A remediation target needs the identifier of the thing it changes.")

    def __str__(self) -> str:
        """Return the target as the one line a reviewer reads."""
        return f"{self.identifier}@{self.environment}" if self.environment else self.identifier

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this target."""
        return {
            "identifier": self.identifier,
            "environment": self.environment,
            "node_id": self.node_id,
            "kind": self.kind,
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> RemediationTarget:
        """Return the target a stored record describes."""
        node = record.get("node_id")
        return cls(
            identifier=str(record.get("identifier", "")),
            environment=str(record.get("environment", "")),
            node_id=str(node) if node else None,
            kind=str(record.get("kind", "workload")),
        )


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """What a target looked like at one instant, and whether anybody could tell.

    ``sub_targets`` is the list of pieces an action may act on individually —
    the pods behind a deployment, the nodes in a pool. It is read before the
    action so partial success can be expressed against something recorded rather
    than against whatever the failure happened to mention.
    """

    target: str
    observed_at: datetime
    values: Mapping[str, Any] = field(default_factory=dict)
    sub_targets: tuple[str, ...] = ()
    known: bool = True

    @property
    def fingerprint(self) -> str:
        """Return the stable fingerprint of the observed values."""
        return fingerprint_of(dict(self.values)) if self.known else _UNKNOWN_FINGERPRINT

    def matches(self, other: StateSnapshot) -> bool:
        """Return whether ``other`` observed the same state this did.

        An unknown snapshot matches nothing, including another unknown one. Two
        failed reads agreeing that they failed is not evidence the target is
        unchanged, and treating it as such is how a rollback lands blind.
        """
        return self.known and other.known and self.fingerprint == other.fingerprint

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this snapshot."""
        return {
            "target": self.target,
            "observed_at": self.observed_at.isoformat(),
            "values": dict(self.values),
            "sub_targets": list(self.sub_targets),
            "known": self.known,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> StateSnapshot:
        """Return the snapshot a stored record describes."""
        return cls(
            target=str(record.get("target", "")),
            observed_at=datetime.fromisoformat(str(record["observed_at"])),
            values=_mapping(record.get("values")),
            sub_targets=tuple(str(name) for name in _sequence(record.get("sub_targets"))),
            known=bool(record.get("known", True)),
        )

    @classmethod
    def unreadable(cls, target: str, *, at: datetime) -> StateSnapshot:
        """Return the snapshot that says the target could not be read.

        A named constructor rather than ``StateSnapshot(known=False)`` at each
        call site, because the whole value of the flag is that every caller
        spells it the same way and none of them writes an empty snapshot by
        accident.
        """
        return cls(target=target, observed_at=at, known=False)


_UNKNOWN_FINGERPRINT = "unknown"


@dataclass(frozen=True, slots=True)
class RemediationEvidence:
    """One observation that motivated a proposed action.

    Carried onto the approval request, because the reviewer's question is not
    "may this run" but "is this the right thing to do", and the second is
    unanswerable without what the agent saw.
    """

    summary: str
    reference: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this observation."""
        return {"summary": self.summary, "reference": self.reference}

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> RemediationEvidence:
        """Return the observation a stored record describes."""
        return cls(
            summary=str(record.get("summary", "")),
            reference=str(record.get("reference", "")),
        )


@dataclass(frozen=True, slots=True)
class RemediationAction:
    """A proposed production change: what, where, why, and on whose behalf.

    Frozen, and it never carries its own decision. Whether this may run is the
    gate's answer and the approval service's record; an action that could hold
    "approved" would be one a caller could construct as approved.
    """

    action_id: str
    capability: str
    target: RemediationTarget
    side_effect_level: SideEffectLevel
    requester: str
    intent: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[RemediationEvidence, ...] = ()
    run_id: str = ""
    team_node_id: str | None = None
    #: The capability's declared risk class, carried rather than looked up. The
    #: policy engine resolves against it, and an approval that was queued and
    #: comes back an hour later must be decided against the class the capability
    #: declared when it was proposed rather than whatever it says now.
    risk_class: str = ""
    #: Whether a rollback plan exists for this capability at all. An action with
    #: none requires approval at every autonomy level, so a decision that could
    #: not answer it is one that cannot be made.
    rollback_planned: bool = False
    #: The exact operation a person could run instead, when the capability can
    #: render one. What a proposal is for.
    operation: str = ""

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("A remediation action needs an identifier.")
        if not self.capability:
            raise ValueError("A remediation action needs the capability that performs it.")
        if not self.requester:
            raise ValueError("A remediation action needs the principal proposing it.")

    @property
    def needs_approval(self) -> bool:
        """Return whether this action's level is above ``read_sensitive``."""
        return self.side_effect_level.needs_approval

    def summary(self) -> str:
        """Return the one line a notification and a queue listing show."""
        return f"{self.capability} on {self.target} requested by {self.requester}"

    def to_payload(self) -> dict[str, Any]:
        """Return the fields a remediation approval carries beyond its diff.

        Complete enough to rebuild the action from, deliberately. The thing that
        executes after an approval must act on what was approved rather than on
        what some process happened to still hold in memory — which is also what
        makes an approval survive the replica that raised it being restarted.
        """
        return {
            "action_id": self.action_id,
            REMEDIATION_PAYLOAD_CAPABILITY: self.capability,
            REMEDIATION_PAYLOAD_ARGUMENTS: dict(self.arguments),
            REMEDIATION_PAYLOAD_ENVIRONMENT: self.target.environment,
            REMEDIATION_PAYLOAD_EVIDENCE: [item.to_record() for item in self.evidence],
            "target": self.target.to_record(),
            "side_effect_level": self.side_effect_level.value,
            "requester": self.requester,
            "intent": self.intent,
            "run_id": self.run_id,
            "team_node_id": self.team_node_id,
            "risk_class": self.risk_class,
            "rollback_planned": self.rollback_planned,
            "operation": self.operation,
        }

    @classmethod
    def of_payload(cls, payload: Mapping[str, Any]) -> RemediationAction:
        """Return the action a stored approval payload describes."""
        team = payload.get("team_node_id")
        return cls(
            action_id=str(payload.get("action_id", "")),
            capability=str(payload.get(REMEDIATION_PAYLOAD_CAPABILITY, "")),
            target=RemediationTarget.of_record(_mapping(payload.get("target"))),
            side_effect_level=SideEffectLevel(str(payload.get("side_effect_level"))),
            requester=str(payload.get("requester", "")),
            intent=str(payload.get("intent", "")),
            arguments=_mapping(payload.get(REMEDIATION_PAYLOAD_ARGUMENTS)),
            evidence=tuple(
                RemediationEvidence.of_record(item)
                for item in _records(payload.get(REMEDIATION_PAYLOAD_EVIDENCE))
            ),
            run_id=str(payload.get("run_id", "")),
            team_node_id=str(team) if team else None,
            risk_class=str(payload.get("risk_class", "")),
            rollback_planned=bool(payload.get("rollback_planned", False)),
            operation=str(payload.get("operation", "")),
        )


@dataclass(frozen=True, slots=True)
class RollbackStep:
    """One step of undoing an action, as a capability call against one piece.

    ``sub_target`` is what makes partial-success scoping possible. A step that
    covers the target as a whole carries ``WHOLE_TARGET`` and survives any
    scoping; a step that names a pod is dropped when that pod was never touched.
    """

    ordinal: int
    description: str
    capability: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    sub_target: str = WHOLE_TARGET

    def to_stored(self) -> StoredRollbackStep:
        """Return the store's form of this step, sub-target folded into arguments."""
        arguments = dict(self.arguments)
        if self.sub_target:
            arguments["sub_target"] = self.sub_target
        return StoredRollbackStep(
            ordinal=self.ordinal,
            description=self.description,
            capability=self.capability,
            arguments=arguments,
        )

    @classmethod
    def of_stored(cls, step: StoredRollbackStep) -> RollbackStep:
        """Return the step a stored record describes."""
        arguments = dict(step.arguments)
        sub_target = str(arguments.pop("sub_target", WHOLE_TARGET))
        return cls(
            ordinal=step.ordinal,
            description=step.description,
            capability=step.capability,
            arguments=arguments,
            sub_target=sub_target,
        )


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """How a proposed action would be undone, written before it is allowed to run.

    ``recorded_state`` is not decoration. It is what the executor compares the
    target against before applying anything, and the comparison is the whole
    control: a plan is a description of how to get back to a state, and applying
    it to a different state is not a rollback.

    ``waived`` exists for the actions whose undo genuinely cannot be derived —
    a cache clear has no inverse. An operator may waive the requirement
    explicitly and the waiver is audited, which is different in kind from a plan
    that silently was not produced.
    """

    plan_id: str
    action_id: str
    target: str
    recorded_state: StateSnapshot
    summary: str = ""
    steps: tuple[RollbackStep, ...] = ()
    reversible: bool = True
    waived: bool = False
    waived_by: str = ""
    waiver_reason: str = ""
    created_at: datetime | None = None
    #: What the target looked like once the action had run — stamped by the
    #: executor, absent until then. Two snapshots rather than one because they
    #: answer two different questions: ``recorded_state`` is where the undo goes,
    #: and this is what the undo expects to find. Checking against the first
    #: would refuse every legitimate rollback, since the action's whole effect is
    #: that the target no longer looks like that.
    applied_state: StateSnapshot | None = None

    # Two things are deliberately *not* checked in a constructor here, and both
    # for the same reason: this type is built at three moments and only one of
    # them is the one worth guarding.
    #
    # Identity is assigned by ``PlanFactory``, so a capability's generator has
    # none to supply; ``to_stored`` refuses a plan that never got one, which
    # puts the check at the boundary that matters.
    #
    # Emptiness is refused by ``PlanFactory`` too, because an empty *derived*
    # plan is the no-derivable-plan case and goes down the waiver path. An empty
    # *scoped* plan is correct and common: an action that changed nothing has
    # nothing to undo, and rejecting it here would make the honest answer
    # unrepresentable.

    @property
    def is_derivable(self) -> bool:
        """Return whether this plan describes an undo somebody could run."""
        return bool(self.steps) and self.reversible

    @property
    def expected_state(self) -> StateSnapshot:
        """Return what the target should look like when this plan is applied.

        The post-execution snapshot once there is one, and the pre-execution one
        before that. A plan whose action never ran describes a target that has
        not moved, so the earlier snapshot is the honest expectation for it.
        """
        return self.applied_state if self.applied_state is not None else self.recorded_state

    def applied_to(self, observed: StateSnapshot) -> RollbackPlan:
        """Return this plan stamped with the state the action left behind."""
        return replace(self, applied_state=observed)

    def within_window(
        self,
        now: datetime,
        *,
        window_seconds: float = REMEDIATION_ROLLBACK_WINDOW_SECONDS,
    ) -> bool:
        """Return whether ``now`` is still inside the one-click rollback window."""
        if self.created_at is None:
            return True
        return now < self.created_at + timedelta(seconds=window_seconds)

    def scoped_to(self, changed: Sequence[str]) -> RollbackPlan:
        """Return this plan covering only ``changed``, ordinals renumbered.

        Steps naming no sub-target are kept whenever anything changed at all:
        they are the ones that act on the target as a whole, and an action that
        moved a replica count moved it once regardless of how many pods came
        back. Nothing is kept when nothing changed, because a rollback plan for
        an action that did not happen is an instruction to make a change nobody
        asked for.
        """
        touched = set(changed)
        if not touched:
            return replace(self, steps=(), summary=_NOTHING_CHANGED, reversible=self.reversible)

        kept = [
            step
            for step in self.steps
            if step.sub_target == WHOLE_TARGET or step.sub_target in touched
        ]
        renumbered = tuple(
            replace(step, ordinal=position) for position, step in enumerate(kept, start=1)
        )
        return replace(self, steps=renumbered)

    def waived_by_operator(self, principal_id: str, reason: str) -> RollbackPlan:
        """Return this plan with the missing-plan requirement explicitly waived."""
        if not reason.strip():
            raise ValueError(
                "A rollback waiver must say why the action is worth running without an "
                "undo. An unexplained waiver is the audit line nobody can act on."
            )
        return replace(self, waived=True, waived_by=principal_id, waiver_reason=reason)

    def to_stored(self, approval_id: str) -> StoredRollbackPlan:
        """Return the store record this plan is held as.

        Raises when the plan never got an identifier. A plan in the store that
        nothing can name again is a plan nobody can apply, which is the same as
        not having one — and the moment to notice is before the approval it
        would have authorised.
        """
        if not self.plan_id:
            raise ValueError(
                f"The plan for {self.action_id!r} has no identifier, so nothing could ask "
                f"for it back. Plans are identified by PlanFactory before they are stored."
            )
        return StoredRollbackPlan(
            plan_id=self.plan_id,
            approval_id=approval_id,
            steps=tuple(step.to_stored() for step in self.steps),
            created_at=self.created_at,
            notes=_notes(self),
        )

    def to_record(self) -> dict[str, Any]:
        """Return the payload form a remediation approval carries the plan in."""
        return {
            "plan_id": self.plan_id,
            "action_id": self.action_id,
            "target": self.target,
            "summary": self.summary,
            "reversible": self.reversible,
            "waived": self.waived,
            "waived_by": self.waived_by,
            "waiver_reason": self.waiver_reason,
            "recorded_state": self.recorded_state.to_record(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            REMEDIATION_PAYLOAD_STEPS: [
                {
                    "ordinal": step.ordinal,
                    "description": step.description,
                    "capability": step.capability,
                    "arguments": dict(step.arguments),
                    "sub_target": step.sub_target,
                }
                for step in self.steps
            ],
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> RollbackPlan:
        """Return the plan a stored payload describes."""
        created = record.get("created_at")
        return cls(
            plan_id=str(record.get("plan_id", "")),
            action_id=str(record.get("action_id", "")),
            target=str(record.get("target", "")),
            recorded_state=StateSnapshot.of_record(_mapping(record.get("recorded_state"))),
            summary=str(record.get("summary", "")),
            steps=tuple(
                RollbackStep(
                    ordinal=int(step.get("ordinal", position)),
                    description=str(step.get("description", "")),
                    capability=str(step.get("capability", "")),
                    arguments=_mapping(step.get("arguments")),
                    sub_target=str(step.get("sub_target", WHOLE_TARGET)),
                )
                for position, step in enumerate(
                    _records(record.get(REMEDIATION_PAYLOAD_STEPS)), start=1
                )
            ),
            reversible=bool(record.get("reversible", True)),
            waived=bool(record.get("waived", False)),
            waived_by=str(record.get("waived_by", "")),
            waiver_reason=str(record.get("waiver_reason", "")),
            created_at=datetime.fromisoformat(str(created)) if created else None,
        )


_NOTHING_CHANGED = "Nothing changed, so there is nothing to undo."


def _notes(plan: RollbackPlan) -> str:
    """Return the sentence the store keeps beside the steps."""
    if plan.waived:
        return (
            f"No rollback is derivable. {plan.waived_by or 'An operator'} waived the "
            f"requirement: {plan.waiver_reason}"
        )
    return plan.summary


@dataclass(frozen=True, slots=True)
class SubTargetResult:
    """What happened to one piece of the target.

    ``changed`` rather than ``succeeded``, because they are different questions
    and only the first decides what goes in the rollback plan. A pod that was
    already in the desired state was not changed and must not be listed as
    something to put back.
    """

    identifier: str
    changed: bool
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this result."""
        return {"identifier": self.identifier, "changed": self.changed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Divergence:
    """One way the resulting state differs from the state that was intended."""

    field_name: str
    intended: Any
    actual: Any

    def describe(self) -> str:
        """Return the one line a divergence report shows for this field."""
        return f"{self.field_name}: intended {self.intended!r}, found {self.actual!r}"

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this divergence."""
        return {"field": self.field_name, "intended": self.intended, "actual": self.actual}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Whether the change took effect, and where it did not.

    Produced by reading the target back rather than by trusting the call that
    made the change. "The API returned 200" and "the change took effect" are
    different claims, and conflating them is how a silent partial failure gets
    reported as a fix.
    """

    target: str
    verified_at: datetime
    divergences: tuple[Divergence, ...] = ()
    observed: StateSnapshot | None = None

    @property
    def converged(self) -> bool:
        """Return whether the actual state matched the intended one."""
        return not self.divergences

    def describe(self) -> str:
        """Return what an operator is shown about the result."""
        if self.observed is not None and not self.observed.known:
            return (
                f"{self.target} could not be read back after the change, so whether it "
                f"took effect is unknown. Treat that as unverified, not as verified."
            )
        if self.converged:
            return f"{self.target} matches the intended state."
        listed = "; ".join(divergence.describe() for divergence in self.divergences)
        return f"{self.target} diverged from the intended state: {listed}"

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this report."""
        return {
            "target": self.target,
            "verified_at": self.verified_at.isoformat(),
            "converged": self.converged,
            "divergences": [divergence.to_record() for divergence in self.divergences],
            "observed": self.observed.to_record() if self.observed is not None else None,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """What one action did, per sub-target, with the plan that reverses it.

    Persisted into the run trace, so an investigation's own record answers "what
    did this change" without a second system to correlate against.
    """

    action_id: str
    capability: str
    target: str
    outcome: ExecutionOutcome
    started_at: datetime
    finished_at: datetime
    plan_id: str = ""
    approval_id: str = ""
    autonomous: bool = False
    results: tuple[SubTargetResult, ...] = ()
    verification: VerificationReport | None = None
    error: str = ""

    @property
    def changed_sub_targets(self) -> tuple[str, ...]:
        """Return the pieces of the target this execution actually altered."""
        return tuple(result.identifier for result in self.results if result.changed)

    @property
    def duration_seconds(self) -> float:
        """Return how long the execution took, end to end."""
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def diverged(self) -> bool:
        """Return whether verification found the result differing from the intent."""
        return self.verification is not None and not self.verification.converged

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is what the run trace holds."""
        return {
            "action_id": self.action_id,
            "capability": self.capability,
            "target": self.target,
            "outcome": self.outcome.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "plan_id": self.plan_id,
            "approval_id": self.approval_id,
            "autonomous": self.autonomous,
            "results": [result.to_record() for result in self.results],
            "verification": (
                self.verification.to_record() if self.verification is not None else None
            ),
            "error": self.error,
        }


def outcome_of(results: Sequence[SubTargetResult], *, expected: Sequence[str]) -> ExecutionOutcome:
    """Return the outcome ``results`` describe against the pieces that were expected.

    Expected rather than attempted, because an action that never reached three
    of its five sub-targets produced no result for them at all — and counting
    only what came back would report a partial as a success.

    An empty ``results`` and a ``results`` that is entirely ``changed=False``
    are different facts and must not share an outcome. The first is a control
    plane that was asked and came back with nothing at all — a real failure.
    The second is a control plane that answered for every piece it was asked
    about and found none of them needed moving, which is
    :class:`SubTargetResult`'s own documented meaning of ``changed=False``: a
    piece already in the desired state, not a piece that failed to change.
    """
    if not results:
        return ExecutionOutcome.FAILED
    changed = [result for result in results if result.changed]
    if not changed:
        return ExecutionOutcome.UNCHANGED
    if len(changed) < len(expected) or len(results) < len(expected):
        return ExecutionOutcome.PARTIAL
    return ExecutionOutcome.SUCCEEDED


def remediation_payload(
    action: RemediationAction,
    *,
    plan: RollbackPlan,
    blast_radius: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return everything a remediation approval request carries.

    Assembled in one function so the reviewer's diff, the allow-list
    re-evaluation, and the executor all read the same payload rather than three
    slightly different ones. The keys are named in the constants tier for the
    same reason: a second spelling is a field that reads back missing with no
    error anywhere.

    The step's own description is never ``action.intent``. ``intent`` already
    travels whole, at the top level of this same payload
    (``RemediationAction.to_payload``), and is what a reviewer reads as *why*
    the action needs approval — printing it again here as *what* the action
    does would have the card state one fact twice rather than two facts once
    each. ``action.operation`` names the capability against its own arguments,
    which is what a step genuinely has to say once the justification lives
    elsewhere; ``action.summary()`` only stands in for the rare action built
    without one (a reader that never went through the gate).
    """
    payload = action.to_payload()
    payload[REMEDIATION_PAYLOAD_STEPS] = [
        {
            "capability": action.capability,
            "description": action.operation or action.summary(),
            "arguments": dict(action.arguments),
        }
    ]
    payload[REMEDIATION_PAYLOAD_ROLLBACK] = [
        {
            "capability": step.capability,
            "description": step.description,
            "arguments": dict(step.arguments),
        }
        for step in plan.steps
    ]
    payload[REMEDIATION_PAYLOAD_WAIVER] = plan.to_record()
    payload[REMEDIATION_PAYLOAD_BLAST_RADIUS] = dict(blast_radius) if blast_radius else {}
    return payload


def utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


def _mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a plain dict, or an empty one if it is not a mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    """Return ``value`` as a tuple, or an empty one if it is not a sequence."""
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        return ()
    return tuple(value)


def _records(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Return the mappings in ``value``, dropping anything that is not one."""
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


__all__ = [
    "WHOLE_TARGET",
    "Divergence",
    "ExecutionOutcome",
    "ExecutionRecord",
    "RemediationAction",
    "RemediationEvidence",
    "RemediationTarget",
    "RollbackPlan",
    "RollbackStep",
    "StateSnapshot",
    "SubTargetResult",
    "VerificationReport",
    "outcome_of",
    "remediation_payload",
    "utc_now",
]
