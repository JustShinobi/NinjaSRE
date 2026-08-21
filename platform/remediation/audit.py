"""What a production change leaves behind, identically however it was authorised.

The requirement worth stating plainly: an autonomous execution is audited *the
same way* as an approved one. Not similarly, not with a subset of the fields —
the same action name, the same resource, the same detail keys. An organisation
reviewing "every production change last month" writes one query, and a second
shape would mean the autonomous half quietly did not appear in it.

What differs is one boolean and one extra obligation. The boolean says nobody
was asked; the obligation is that the team is told afterwards. Autonomy that
nobody hears about is autonomy nobody can withdraw, because the first anyone
learns of it is the incident it caused.

Four things are recorded here:

* **the execution**, whatever its outcome — a refused action is a fact about the
  system too, and one an operator tuning an allow-list needs;
* **the rollback**, with which steps ran, because a partial undo is the state
  somebody has to reason about next;
* **the waiver**, when an operator accepted an action that cannot be undone;
* **the kill switch**, both directions, because "who stopped writes and when" is
  the first question after a stop nobody expected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    AUDIT_DETAIL_TARGET,
    AUDIT_DETAIL_TARGET_FINGERPRINT,
    REMEDIATION_AUDIT_ACTION_AUTONOMOUS,
    REMEDIATION_AUDIT_ACTION_KILL_SWITCH,
    REMEDIATION_AUDIT_ACTION_WAIVER,
    REMEDIATION_AUDIT_RESOURCE_KIND,
)
from platform.identity.audit.recorder import (
    REMEDIATION_AUDIT_ACTION_EXECUTE,
    REMEDIATION_AUDIT_ACTION_ROLLBACK,
    AuditContext,
    AuditRecorder,
)
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope
from platform.remediation.autonomy.kill_switch import KillSwitchState
from platform.remediation.models import (
    ExecutionOutcome,
    ExecutionRecord,
    RemediationAction,
    RollbackPlan,
)

_LOG = get_logger(__name__)


@runtime_checkable
class TeamNotifier(Protocol):
    """Whatever tells a team that something ran without asking them.

    A protocol rather than a chat client, because which surface a team watches
    is a deployment's decision and because the obligation this expresses —
    somebody is told — must not depend on any particular one being configured.
    """

    async def autonomous_execution(
        self, action: RemediationAction, record: ExecutionRecord
    ) -> None:
        """Tell ``action``'s team that it ran without an approval."""


@dataclass(slots=True)
class RemediationAuditor:
    """Writes the remediation audit trail, and tells the team when nobody was asked.

    The recorder is optional so a deployment mid-wiring still executes rather
    than failing at the audit call — but the log line is not, and it carries the
    same fields, so an operator whose database was down still has the record in
    whatever ships their logs.
    """

    scope: TenantScope
    recorder: AuditRecorder | None = None
    notifier: TeamNotifier | None = None
    #: Named once, so an autonomous execution's audit rows attribute to the same
    #: actor everywhere rather than to whichever string a call site passed.
    autonomous_actor: str = "ninjasre-autonomy"
    _outcomes: dict[ExecutionOutcome, AuditOutcome] = field(
        default_factory=lambda: {
            ExecutionOutcome.SUCCEEDED: AuditOutcome.ALLOWED,
            ExecutionOutcome.PARTIAL: AuditOutcome.ALLOWED,
            ExecutionOutcome.FAILED: AuditOutcome.DENIED,
            ExecutionOutcome.REFUSED: AuditOutcome.DENIED,
        },
        repr=False,
    )

    async def executed(
        self,
        action: RemediationAction,
        record: ExecutionRecord,
        *,
        autonomous: bool = False,
        context: AuditContext | None = None,
    ) -> None:
        """Record one execution, and notify the team when nobody approved it."""
        detail: dict[str, Any] = {
            AUDIT_DETAIL_TARGET: record.target,
            "capability": action.capability,
            "outcome": record.outcome.value,
            "autonomous": autonomous,
            "approval_id": record.approval_id,
            "plan_id": record.plan_id,
            "changed": list(record.changed_sub_targets),
            "diverged": record.diverged,
            "duration_seconds": record.duration_seconds,
        }
        if record.verification is not None:
            detail["verification"] = record.verification.to_record()
        if record.error:
            detail["error"] = record.error

        await self._record(
            action,
            action_name=REMEDIATION_AUDIT_ACTION_EXECUTE,
            outcome=self._outcomes[record.outcome],
            detail=detail,
            context=context,
            autonomous=autonomous,
        )

        if not autonomous:
            return

        await self._record(
            action,
            action_name=REMEDIATION_AUDIT_ACTION_AUTONOMOUS,
            outcome=self._outcomes[record.outcome],
            detail=detail,
            context=context,
            autonomous=True,
        )
        await self._notify(action, record)

    async def rolled_back(
        self,
        action: RemediationAction,
        plan: RollbackPlan,
        *,
        completed: Sequence[int],
        verified: bool,
        context: AuditContext | None = None,
    ) -> None:
        """Record one rollback, including a partial one."""
        await self._record(
            action,
            action_name=REMEDIATION_AUDIT_ACTION_ROLLBACK,
            outcome=AuditOutcome.ALLOWED if verified else AuditOutcome.DENIED,
            detail={
                AUDIT_DETAIL_TARGET: plan.target,
                AUDIT_DETAIL_TARGET_FINGERPRINT: plan.recorded_state.fingerprint,
                "plan_id": plan.plan_id,
                "completed_steps": list(completed),
                "steps": len(plan.steps),
                "verified": verified,
            },
            context=context,
        )

    async def waived(
        self,
        action: RemediationAction,
        plan: RollbackPlan,
        *,
        context: AuditContext | None = None,
    ) -> None:
        """Record that an operator accepted an action that cannot be undone."""
        await self._record(
            action,
            action_name=REMEDIATION_AUDIT_ACTION_WAIVER,
            outcome=AuditOutcome.ALLOWED,
            detail={
                AUDIT_DETAIL_TARGET: plan.target,
                "plan_id": plan.plan_id,
                "granted_by": plan.waived_by,
                "reason": plan.waiver_reason,
                "capability": action.capability,
            },
            context=context,
        )

    async def kill_switch(
        self,
        state: KillSwitchState | None,
        *,
        engaged: bool,
        actor_id: str,
        context: AuditContext | None = None,
    ) -> None:
        """Record the switch going on or off, and by whom.

        Both directions. A release is the more sensitive of the two — it is the
        moment automated writes become possible again — and an audit trail that
        only recorded stops would leave the restart unattributed.
        """
        detail: dict[str, Any] = {"engaged": engaged}
        if state is not None:
            detail.update(state.to_record())

        _LOG.warning(
            "remediation.kill_switch_audited",
            engaged=engaged,
            actor_id=actor_id,
            scope=state.scope if state is not None else "",
        )
        if self.recorder is None:
            return
        await self.recorder.record(
            self.scope,
            context if context is not None else _context(actor_id),
            action=REMEDIATION_AUDIT_ACTION_KILL_SWITCH,
            resource_kind=REMEDIATION_AUDIT_RESOURCE_KIND,
            resource_id=state.scope if state is not None else "*",
            outcome=AuditOutcome.ALLOWED,
            detail=detail,
        )

    async def _record(
        self,
        action: RemediationAction,
        *,
        action_name: str,
        outcome: AuditOutcome,
        detail: Mapping[str, Any],
        context: AuditContext | None,
        autonomous: bool = False,
    ) -> None:
        """Write one audit row, and log it whether or not there is somewhere to write."""
        _LOG.info(
            "remediation.audited",
            audit_action=action_name,
            action_id=action.action_id,
            capability=action.capability,
            target=str(action.target),
            outcome=outcome.value,
        )
        if self.recorder is None:
            return
        await self.recorder.record(
            self.scope,
            context if context is not None else self._context_for(action, autonomous=autonomous),
            action=action_name,
            resource_kind=REMEDIATION_AUDIT_RESOURCE_KIND,
            resource_id=action.action_id,
            outcome=outcome,
            detail=detail,
        )

    def _context_for(self, action: RemediationAction, *, autonomous: bool) -> AuditContext:
        """Return who an unattributed remediation row is recorded against.

        An autonomous run is attributed to the platform rather than to the agent
        that proposed it. The agent asked; nobody decided; saying the agent
        decided would put a principal on the row who never had the authority.
        """
        if autonomous:
            return AuditContext(actor_kind=ActorKind.SYSTEM, actor_id=self.autonomous_actor)
        return _context(action.requester)

    async def _notify(self, action: RemediationAction, record: ExecutionRecord) -> None:
        """Tell the team an action ran without them, never letting that stop anything."""
        if self.notifier is None:
            _LOG.warning(
                "remediation.autonomous_unnotified",
                action_id=action.action_id,
                capability=action.capability,
                team=action.team_node_id,
            )
            return
        try:
            await self.notifier.autonomous_execution(action, record)
        except Exception as failure:  # noqa: BLE001 — the change already happened
            _LOG.error(
                "remediation.autonomous_notification_failed",
                action_id=action.action_id,
                error=str(failure),
            )


def _context(actor_id: str) -> AuditContext:
    """Return the acting context for a principal with no request context to carry."""
    return AuditContext(actor_kind=ActorKind.USER, actor_id=actor_id)


__all__ = [
    "RemediationAuditor",
    "TeamNotifier",
]
