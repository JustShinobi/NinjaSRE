"""Running an approved change: isolated, serialised, recorded per piece, verified.

Everything before this module decides whether the action may happen. This is
where it does, and four things about how are load-bearing.

**It runs inside the deployment's sandbox profile, through the credential
proxy.** The applier is handed an ``ExecutionEnvironment``, which names the
sandbox instance it is running in and the proxy address it reaches the control
plane through. There is no parameter on it that could carry a credential — only
a handle — which is the same shape the proxy client uses one tier up, and it is
why an applier cannot be called outside an isolation profile at all.

**Concurrent actions on one target are serialised.** Two mitigations for one
workload during an incident is normal; two of them interleaving is how a scale
and a restart produce a state neither engineer proposed. The lock is per target,
held for the whole apply-and-verify, and it times out rather than waiting
forever.

**Conditions are re-evaluated here, not only when the action was proposed.** An
approval can sit pending for ten minutes, and a blast radius that was two
services when a human looked at it may be twenty now. This is the second
evaluation, and it is the one that decides.

**Partial success is recorded per sub-target and narrows the plan.** Three of
five pods restarted produces three results, an outcome of ``partial``, and a
rollback plan covering three. A plan that still covered five would be an
instruction to change two things nobody touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.closed_loop import SECOND_ARRIVAL_REFUSE, SECOND_ARRIVAL_WAIT
from config.constants.security import (
    NINJASRE_CREDENTIAL_PROXY_URL_ENV,
    REMEDIATION_TARGET_LOCK_TIMEOUT_SECONDS,
)
from platform.observability.logging import get_logger
from platform.remediation.aftermath import PlanApplier, undo_payload
from platform.remediation.audit import RemediationAuditor
from platform.remediation.autonomy.evaluation import ConditionEvaluator
from platform.remediation.autonomy.kill_switch import KillSwitch
from platform.remediation.components import ComponentRegistry
from platform.remediation.errors import TargetLocked
from platform.remediation.models import (
    ExecutionOutcome,
    ExecutionRecord,
    RemediationAction,
    RollbackPlan,
    StateSnapshot,
    SubTargetResult,
    outcome_of,
    utc_now,
)
from platform.remediation.obligations import VerificationRecorder
from platform.remediation.verification import OutcomeVerification

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    """Where one action runs, and how it reaches the thing it is changing.

    A value rather than an ambient setting, and handed to the applier rather
    than read by it. That is what makes "every remediation ran in a sandbox,
    through the proxy" checkable by looking at one signature instead of by
    auditing seven appliers — and there is deliberately no field here that could
    hold a secret, only the handle that names one.
    """

    sandbox_id: str
    profile: str
    proxy_url: str = ""
    credential_handle: str = ""
    scratch_path: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the execution record carries."""
        return {
            "sandbox_id": self.sandbox_id,
            "profile": self.profile,
            "proxied": bool(self.proxy_url),
        }


@runtime_checkable
class ExecutionIsolation(Protocol):
    """Provisions the sandbox one action runs inside, and releases it afterwards.

    A protocol rather than the sandbox port itself, because what this package
    needs is narrower than the six operations a sandbox has: provision it, name
    it, put it away. Depending on the wider interface would let a future caller
    reach ``execute`` from here and run a command outside the applier that was
    approved.
    """

    def running(self, action: RemediationAction) -> Any:
        """Return an async context manager yielding the environment for ``action``."""


class SecondArrival(StrEnum):
    """What the second remediation against one resource does. Declared, per FR-021.

    Two behaviours, both correct in different deployments, and the requirement
    is that a deployment says which rather than that one is right. Waiting suits
    an estate where the second action is usually a different fix for the same
    incident and running it afterwards is fine; refusing suits one where a
    second arrival almost always means two investigations have reached the same
    workload and one of them should stop rather than queue.
    """

    #: Queue behind the first, up to the lock timeout, then refuse.
    WAIT = SECOND_ARRIVAL_WAIT
    #: Refuse immediately, naming the action that holds the target.
    REFUSE = SECOND_ARRIVAL_REFUSE


@runtime_checkable
class ResourceHold(Protocol):
    """A cross-replica hold on one target, when a deployment has one.

    A seam rather than an implementation. ``TargetLocks`` below serialises the
    actions *this* replica is executing, which is the case that actually happens
    — an agent proposing two mitigations for one workload in one investigation.
    A deployment running several replicas that wants the guarantee across all of
    them supplies this, and the executor holds it for exactly the same span as
    the in-process lock.
    """

    async def acquire(self, target: str, *, holder: str) -> bool:
        """Return whether ``holder`` now holds ``target``, without waiting."""

    async def release(self, target: str, *, holder: str) -> None:
        """Release ``target`` if ``holder`` still holds it."""


@dataclass(slots=True)
class TargetLocks:
    """One advisory lock per target, with a bound on how long anybody waits.

    In-process by default, because the actions being serialised are the ones
    this replica is executing. ``durable`` is the seam for a deployment that
    needs the guarantee across replicas; the two compose, so a deployment with
    one still gets the in-process serialisation first and pays for the round
    trip only when it would actually have run something.

    ``on_conflict`` is the declaration FR-021 asks for. Both behaviours are
    implemented and both are tested, because "wait or be refused" is only a
    guarantee if a deployment can say which and the answer holds.
    """

    timeout_seconds: float = REMEDIATION_TARGET_LOCK_TIMEOUT_SECONDS
    on_conflict: SecondArrival = SecondArrival.WAIT
    durable: ResourceHold | None = None
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    holders: dict[str, str] = field(default_factory=dict)

    @asynccontextmanager
    async def hold(self, target: str, *, holder: str) -> AsyncIterator[None]:
        """Hold ``target``'s lock for the block, or raise naming who has it."""
        lock = self.locks.setdefault(target, asyncio.Lock())
        if self.on_conflict is SecondArrival.REFUSE and lock.locked():
            raise TargetLocked(
                target,
                holder=self.holders.get(target, ""),
                waited_seconds=0.0,
            )
        try:
            await asyncio.wait_for(lock.acquire(), timeout=self.timeout_seconds)
        except TimeoutError as expiry:
            raise TargetLocked(
                target,
                holder=self.holders.get(target, ""),
                waited_seconds=self.timeout_seconds,
            ) from expiry

        if self.durable is not None and not await self.durable.acquire(target, holder=holder):
            lock.release()
            raise TargetLocked(target, holder="another replica", waited_seconds=0.0)

        self.holders[target] = holder
        try:
            yield
        finally:
            self.holders.pop(target, None)
            if self.durable is not None:
                await self.durable.release(target, holder=holder)
            lock.release()

    def held_by(self, target: str) -> str:
        """Return which action currently holds ``target``, or an empty string."""
        return self.holders.get(target, "")


@dataclass(frozen=True, slots=True)
class Execution:
    """One completed execution, with the plan narrowed to what actually changed.

    The plan travels back out because it is what the caller stores and what a
    rollback later applies. Returning the original would hand a caller a plan
    covering five pods after three were restarted, which is the specific way a
    partial success becomes an unreviewed change.
    """

    record: ExecutionRecord
    plan: RollbackPlan

    @property
    def outcome(self) -> ExecutionOutcome:
        """Return how far the execution got."""
        return self.record.outcome

    @property
    def diverged(self) -> bool:
        """Return whether verification found the result differing from the intent."""
        return self.record.diverged


@dataclass(slots=True)
class RemediationExecutor:
    """Runs one approved or allow-listed action, and records what it did.

    The kill switch and the condition evaluator are consulted here *again*, not
    only at the gate. An execution reached through any other entry point — a
    console button, a replayed run, an operator's CLI — passes through this
    object, so the checks that matter cannot be skipped by arriving from a
    different direction.
    """

    registry: ComponentRegistry
    isolation: ExecutionIsolation
    verification: OutcomeVerification
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    evaluator: ConditionEvaluator | None = None
    auditor: RemediationAuditor | None = None
    locks: TargetLocks = field(default_factory=TargetLocks)
    #: Where the obligation to find out whether this worked is written. Optional
    #: because the executor predates it and a deployment that has not wired the
    #: ledger still executes — but a deployment without one presses buttons and
    #: reports that it pressed them, which is the thing feature 041 exists to
    #: stop, so the composition root wires it.
    obligations: VerificationRecorder | None = None
    #: How a half-applied action is put back when the applier raised having
    #: already changed something. Optional for the same reason, and the
    #: consequence of leaving it out is stated in ``_reconcile``'s log line
    #: rather than hidden.
    undo: PlanApplier | None = None
    clock: Callable[[], datetime] = field(default=utc_now)

    async def execute(
        self,
        action: RemediationAction,
        *,
        plan: RollbackPlan,
        before: StateSnapshot,
        approval_id: str = "",
        autonomous: bool = False,
        blast_radius: int = 0,
    ) -> Execution:
        """Run ``action`` and return what happened, with the plan scoped to it.

        The order is the specification. Kill switch first, because it overrides
        an approval that has already been granted. Conditions second, against
        *now* rather than against when the action was proposed. Then the lock,
        then the sandbox, then the change, then the read-back.
        """
        self.kill_switch.check(team_node_id=action.team_node_id)

        at = self.clock()
        if autonomous and self.evaluator is not None:
            evaluation = self.evaluator.evaluate(action, at=at, blast_radius=blast_radius)
            evaluation.raise_if_refused()

        async with self.locks.hold(str(action.target), holder=action.action_id):
            return await self._run(
                action,
                plan=plan,
                before=before,
                approval_id=approval_id,
                autonomous=autonomous,
                started_at=at,
            )

    async def _run(
        self,
        action: RemediationAction,
        *,
        plan: RollbackPlan,
        before: StateSnapshot,
        approval_id: str,
        autonomous: bool,
        started_at: datetime,
    ) -> Execution:
        """Apply the change inside the sandbox, verify it, and assemble the record."""
        components = self.registry.get(action.capability)
        results: tuple[SubTargetResult, ...] = ()
        error = ""

        # Read the signals the capability declares *before* the change. A window
        # read afterwards would contain the action, and every verdict computed
        # from it would understate the effect.
        signals_before = await self._capture(action)

        try:
            async with self.isolation.running(action) as environment:
                results = await components.applier.apply(
                    action, before=before, environment=environment
                )
        except Exception as failure:  # noqa: BLE001 — recorded as an outcome, then re-raised
            error = f"{type(failure).__name__}: {failure}"
            # An applier that raised may still have changed something. Leaving
            # it there would be exactly the half-applied state FR-012 forbids,
            # so the target is read back and put right before anything else.
            await self._reconcile(action, components, before=before, plan=plan)
            record = self._record(
                action,
                plan=plan,
                results=(),
                outcome=ExecutionOutcome.FAILED,
                started_at=started_at,
                approval_id=approval_id,
                autonomous=autonomous,
                error=error,
            )
            await self._audit(action, record, autonomous=autonomous)
            raise

        if self.kill_switch.is_engaged(team_node_id=action.team_node_id):
            # The switch went on while the applier was running. The change has
            # already landed, so abandoning the record here would leave a write
            # nobody could see — the action is completed and recorded, and the
            # switch stops the *next* one.
            _LOG.warning(
                "remediation.kill_switch_engaged_mid_flight",
                action_id=action.action_id,
                capability=action.capability,
                target=str(action.target),
                changed=len([result for result in results if result.changed]),
            )

        outcome = outcome_of(results, expected=before.sub_targets or (str(action.target),))
        scoped = plan.scoped_to([result.identifier for result in results if result.changed])

        report = None
        if outcome.changed_anything:
            report = await self.verification.verify(action, before=before, at=self.clock())
            if report.observed is not None:
                # The plan now knows both states: where the undo goes, and what
                # it expects to find. Without the second, the rollback's target
                # check would compare against the state the action deliberately
                # moved away from and refuse every legitimate undo.
                scoped = scoped.applied_to(report.observed)

        record = self._record(
            action,
            plan=scoped,
            results=results,
            outcome=outcome,
            started_at=started_at,
            approval_id=approval_id,
            autonomous=autonomous,
            error=error,
        )
        record = _with_verification(record, report)

        if autonomous and self.evaluator is not None and outcome.changed_anything:
            self.evaluator.record_execution(action, at=record.finished_at)

        if outcome.changed_anything:
            # The run ends here. Whether it worked is a durable obligation with
            # a due time, not something this call waits for — NFR-002.
            await self._owe(
                action,
                before=signals_before,
                executed_at=record.finished_at,
                autonomous=autonomous,
                plan=scoped,
            )

        await self._audit(action, record, autonomous=autonomous)
        _LOG.info(
            "remediation.executed",
            action_id=action.action_id,
            capability=action.capability,
            target=str(action.target),
            outcome=outcome.value,
            autonomous=autonomous,
            changed=len(record.changed_sub_targets),
            diverged=record.diverged,
        )
        return Execution(record=record, plan=scoped)

    def _record(
        self,
        action: RemediationAction,
        *,
        plan: RollbackPlan,
        results: tuple[SubTargetResult, ...],
        outcome: ExecutionOutcome,
        started_at: datetime,
        approval_id: str,
        autonomous: bool,
        error: str,
    ) -> ExecutionRecord:
        """Return the record of one execution, whatever its outcome."""
        return ExecutionRecord(
            action_id=action.action_id,
            capability=action.capability,
            target=str(action.target),
            outcome=outcome,
            started_at=started_at,
            finished_at=self.clock(),
            plan_id=plan.plan_id,
            approval_id=approval_id,
            autonomous=autonomous,
            results=results,
            error=error,
        )

    async def _audit(
        self,
        action: RemediationAction,
        record: ExecutionRecord,
        *,
        autonomous: bool,
    ) -> None:
        """Audit the execution, identically whether a human approved it or not."""
        if self.auditor is None:
            return
        await self.auditor.executed(action, record, autonomous=autonomous)

    async def _capture(self, action: RemediationAction) -> dict[str, float]:
        """Return the declared signals as they stand, or nothing when unwired."""
        if self.obligations is None:
            return {}
        return dict(await self.obligations.capture(action))

    async def _owe(
        self,
        action: RemediationAction,
        *,
        before: dict[str, float],
        executed_at: datetime,
        autonomous: bool,
        plan: RollbackPlan,
    ) -> None:
        """Write down that somebody has to find out whether this worked."""
        if self.obligations is None:
            return
        await self.obligations.owe(
            action,
            before=before,
            executed_at=executed_at,
            autonomous=autonomous,
            plan_id=plan.plan_id,
            undo=undo_payload(action, plan),
        )

    async def _reconcile(
        self,
        action: RemediationAction,
        components: Any,
        *,
        before: StateSnapshot,
        plan: RollbackPlan,
    ) -> None:
        """Put the target back if a failed apply left it changed. FR-012.

        Read the target, compare it to the state the action started from, and —
        when they differ — apply the plan. An applier that raised having already
        changed something is the ordinary way a kill switch, a network partition
        or a control plane timeout produces a half-applied action, and leaving
        one behind is the single failure this feature is least able to detect
        afterwards: the verification would compare against a "before" that is no
        longer anybody's idea of before.
        """
        after = await components.reader.read(action, at=self.clock())
        if not after.known or before.matches(after):
            return

        if self.undo is None or not plan.is_derivable:
            _LOG.error(
                "remediation.left_half_applied",
                action_id=action.action_id,
                capability=action.capability,
                target=str(action.target),
                reason=(
                    "no rollback runner is wired"
                    if self.undo is None
                    else "no derivable rollback plan"
                ),
            )
            return

        try:
            await self.undo.apply(plan.applied_to(after), action=action, now=self.clock())
        except Exception as refused:  # noqa: BLE001 — the original failure is the one raised
            _LOG.error(
                "remediation.reconcile_failed",
                action_id=action.action_id,
                target=str(action.target),
                error=f"{type(refused).__name__}: {refused}",
            )
            return

        _LOG.warning(
            "remediation.reconciled_after_failure",
            action_id=action.action_id,
            capability=action.capability,
            target=str(action.target),
            plan_id=plan.plan_id,
        )


def _with_verification(
    record: ExecutionRecord,
    report: Any,
) -> ExecutionRecord:
    """Return ``record`` carrying ``report``, or unchanged when there is none."""
    if report is None:
        return record
    from dataclasses import replace

    return replace(record, verification=report)


@dataclass(slots=True)
class SandboxIsolation:
    """Provisions a sandbox for each action and hands back its environment.

    The specification comes from a callable rather than from configuration read
    here, because what an action needs — which team, which investigation, which
    egress allow-list — is known by the composition root and not by this
    package. What this package guarantees is that the applier never runs outside
    whatever came back.
    """

    sandbox: Any
    spec_for: Callable[[RemediationAction], Any]
    proxy_url_env: str = NINJASRE_CREDENTIAL_PROXY_URL_ENV
    proxy_url: str = ""

    @asynccontextmanager
    async def running(self, action: RemediationAction) -> AsyncIterator[ExecutionEnvironment]:
        """Provision, yield the environment, and release even when the action raised."""
        instance = await self.sandbox.provision(self.spec_for(action))
        try:
            yield ExecutionEnvironment(
                sandbox_id=instance.sandbox_id,
                profile=str(instance.profile),
                proxy_url=self.proxy_url,
                scratch_path=instance.scratch_path,
            )
        finally:
            await self.sandbox.release(instance)


@dataclass(slots=True)
class RemediationApplier:
    """What the approval service does when a remediation is approved: nothing yet.

    Deliberately, and this is the one place in the codebase where an applier
    that does not apply is correct. For the other four change types, approval
    *is* the change — writing the configuration node is the whole of it. For a
    production remediation it is not: between the decision and the action there
    are three more steps that a human's click cannot stand in for. The
    conditions have to be re-evaluated against the moment the change actually
    runs, the target has to be locked against a concurrent action, and the
    sandbox has to be provisioned.

    So the approval authorises and ``RemediationExecutor`` performs, and the
    ordering in the plan — approve, persist, re-evaluate, execute — stays true
    rather than being collapsed into one call because it was convenient.

    ``read`` is not a no-op, and it is why this exists as a type at all: it is
    what feature 015's conflict detection fingerprints the target against, so a
    remediation approved against a cluster that has since recovered is caught by
    the same mechanism that catches a configuration edit somebody raced.
    """

    registry: ComponentRegistry
    clock: Callable[[], datetime] = field(default=utc_now)

    async def read(self, target: Any) -> dict[str, Any] | None:
        """Return the target's current observed state, or ``None`` if unreadable.

        ``None`` is what turns "the workload is gone" into an unrecoverable
        conflict rather than into an approval of nothing.
        """
        capability = _capability_of(target)
        if capability is None or not self.registry.has(capability):
            return None

        components = self.registry.get(capability)
        action = _probe_action(target, capability)
        snapshot = await components.reader.read(action, at=self.clock())
        return dict(snapshot.values) if snapshot.known else None

    async def apply(self, change: Any) -> None:
        """Record that the approval was granted; the executor performs the action."""
        _LOG.info(
            "remediation.approval_granted",
            change_id=getattr(change, "change_id", ""),
            target=str(getattr(change, "target", "")),
        )


def _capability_of(target: Any) -> str | None:
    """Return the capability a change target's path names, if it names one."""
    path = getattr(target, "path", None)
    return str(path) if path else None


def _probe_action(target: Any, capability: str) -> RemediationAction:
    """Return the minimal action a state read needs, for a conflict check.

    Minimal on purpose. This is not the action that will run — it is a handle
    the reader uses to name the target, and building a full one here would mean
    inventing a requester and an intent that nobody supplied.
    """
    from core.capability.metadata import SideEffectLevel
    from platform.remediation.models import RemediationTarget

    identifier = str(getattr(target, "identifier", ""))
    name, _, environment = identifier.partition("@")
    return RemediationAction(
        action_id=f"probe:{identifier}",
        capability=capability,
        target=RemediationTarget(identifier=name or identifier, environment=environment),
        side_effect_level=SideEffectLevel.READ,
        requester="conflict-check",
    )


__all__ = [
    "Execution",
    "ExecutionEnvironment",
    "ExecutionIsolation",
    "RemediationApplier",
    "RemediationExecutor",
    "SandboxIsolation",
    "TargetLocks",
]
