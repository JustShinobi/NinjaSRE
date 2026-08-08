"""Every decision this package makes, permitting and refusing alike.

The requirement worth stating plainly: a refusal is audited exactly as an
execution is. Same action name, same resource kind, same detail keys, one
outcome field between them. An operator asking "what did the policy engine
decide last night" writes one query, and a second shape for the refusals would
mean the half that explains why nothing happened is the half that does not
appear.

The explanation goes in the record, not a pointer to it. A decision audited as
"level: act_and_report" and nothing else is a row that cannot be re-derived six
weeks later against a policy set that has since been edited — which is exactly
when somebody asks. So the rules considered, the winner, the bound that refused
and the reason are all in the detail, bounded by the same JSONB limits every
other audit payload obeys.

An autonomous decision is attributed to the platform, never to the agent that
proposed it. The agent asked; nobody decided; a row naming the agent would put a
principal on it who never had the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from config.constants.autonomy import (
    AUTONOMY_AUDIT_ACTION_DECISION,
    AUTONOMY_AUDIT_ACTION_OVERRIDE_EXPIRED,
    AUTONOMY_AUDIT_RESOURCE_KIND,
    AUTONOMY_AUDIT_RESOURCE_KIND_OVERRIDE,
    AUTONOMY_DETAIL_ACTION,
    AUTONOMY_DETAIL_BOUND,
    AUTONOMY_DETAIL_CONSIDERED,
    AUTONOMY_DETAIL_DRY_RUN,
    AUTONOMY_DETAIL_LEVEL,
    AUTONOMY_DETAIL_OUTCOME,
    AUTONOMY_DETAIL_RISK_CLASS,
    AUTONOMY_DETAIL_WINNER,
)
from platform.autonomy.policy import TimedOverride
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope

if TYPE_CHECKING:  # pragma: no cover - import only for the annotation
    from platform.autonomy.decision import Decision

_LOG = get_logger(__name__)

#: Who an autonomous decision is recorded against. Named once so every row
#: attributes to the same actor rather than to whichever string a call site had.
AUTONOMY_ACTOR: str = "ninjasre-autonomy"


@dataclass(slots=True)
class DecisionAuditor:
    """Writes the autonomy trail, and logs it whether or not there is a database.

    The recorder is optional so a deployment mid-wiring still decides rather than
    failing at the audit call. The log line is not optional and carries the same
    fields, so an operator whose database is down still has the record in
    whatever ships their logs.
    """

    scope: TenantScope
    recorder: AuditRecorder | None = None
    actor_id: str = AUTONOMY_ACTOR

    async def decided(self, decision: Decision, *, context: AuditContext | None = None) -> None:
        """Record one decision, whichever way it went."""
        detail = self.detail_of(decision)
        _LOG.info(
            "autonomy.decided",
            action_id=decision.action.action_id,
            capability=decision.action.capability,
            decision=decision.outcome.value,
            level=decision.resolution.level.value,
            refused_by=detail[AUTONOMY_DETAIL_BOUND],
        )
        if self.recorder is None:
            return
        await self.recorder.record(
            self.scope,
            context if context is not None else self._context(),
            action=AUTONOMY_AUDIT_ACTION_DECISION,
            resource_kind=AUTONOMY_AUDIT_RESOURCE_KIND,
            resource_id=decision.action.action_id,
            outcome=(AuditOutcome.ALLOWED if decision.permitted else AuditOutcome.DENIED),
            detail=detail,
        )

    async def override_expired(
        self, override: TimedOverride, *, context: AuditContext | None = None
    ) -> None:
        """Record that a time-bounded override has run out.

        Audibly, per the requirement, and separately from the decisions taken
        under it. An override that simply stopped applying would leave an
        operator reading "this used to be permitted" with no row saying when the
        permission ended or who had granted it.
        """
        _LOG.warning(
            "autonomy.override_expired",
            override=override.name,
            granted_by=override.granted_by,
            expired_at=override.expires_at.isoformat(),
        )
        if self.recorder is None:
            return
        await self.recorder.record(
            self.scope,
            context if context is not None else self._context(),
            action=AUTONOMY_AUDIT_ACTION_OVERRIDE_EXPIRED,
            resource_kind=AUTONOMY_AUDIT_RESOURCE_KIND_OVERRIDE,
            resource_id=override.name,
            outcome=AuditOutcome.ALLOWED,
            detail=override.to_record(),
        )

    def detail_of(self, decision: Decision) -> dict[str, Any]:
        """Return what one decision's audit row carries.

        Public because the run trace and the console read the same shape. Two
        renderings of one decision is two places for it to be described
        differently, and the difference would only ever be found in an argument
        about what the system did.
        """
        resolution = decision.resolution
        return {
            AUTONOMY_DETAIL_OUTCOME: decision.outcome.value,
            AUTONOMY_DETAIL_LEVEL: resolution.level.value,
            AUTONOMY_DETAIL_RISK_CLASS: decision.action.risk_class.value,
            AUTONOMY_DETAIL_WINNER: resolution.winner,
            AUTONOMY_DETAIL_CONSIDERED: [entry.to_record() for entry in resolution.considered],
            AUTONOMY_DETAIL_BOUND: decision.bound.value if decision.bound is not None else "",
            AUTONOMY_DETAIL_DRY_RUN: resolution.dry_run,
            "capability": decision.action.capability,
            "subjects": [subject.resource_id for subject in decision.action.subjects],
            "reason": decision.reason,
            "operation": decision.action.runnable(),
            "budgets_spent": list(decision.budgets_spent),
            "executed": decision.executed,
            "requester": decision.action.requester,
            "run_id": decision.action.run_id,
            # The whole action, not only what a listing renders. A policy change
            # is previewed by *re-deciding* the recorded actions, and a record
            # that kept only the resource identifiers could not answer a rule
            # that selects on a label or a kind — the preview would quietly
            # report no difference where there is one.
            AUTONOMY_DETAIL_ACTION: decision.action.to_record(),
        }

    def _context(self) -> AuditContext:
        """Return the acting context an unattributed autonomy row is recorded against."""
        return AuditContext(actor_kind=ActorKind.SYSTEM, actor_id=self.actor_id)


__all__ = [
    "AUTONOMY_ACTOR",
    "DecisionAuditor",
]
