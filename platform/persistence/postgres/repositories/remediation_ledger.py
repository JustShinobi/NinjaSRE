"""Remediation outcomes in PostgreSQL, with claiming that two replicas can share.

Two queries carry this repository and both are worth reading before changing.

``claim_due`` selects ``FOR UPDATE SKIP LOCKED`` and stamps the lease in the
same transaction. That is what makes claiming atomic per obligation: two workers
asking at the same instant divide the due rows between them, and neither waits
for the other. A select followed by an update would let both see a row before
either wrote, and the consequence is not a duplicated log line — it is one
change rolled back twice.

``effectiveness`` counts in the database, grouped by verdict. It is asked on the
path of a proposal over a year of history, and the alternative is fetching the
year to add it up in Python. The partial index on the due rows and the composite
index on ``(resource, capability, condition, executed_at)`` are what make both
of those lookups rather than scans.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from config.constants.closed_loop import (
    MAX_RECURRING_PROBLEM_PAGE_SIZE,
    MAX_VERIFICATION_CLAIM_BATCH,
    VERIFICATION_LEASE_SECONDS,
)
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    EffectivenessSummary,
    RecurringProblem,
    RemediationOutcome,
    RollbackDisposition,
    VerificationState,
    VerificationVerdict,
    check_claim_batch,
    check_effectiveness_limit,
    check_problem_limit,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_tuple,
    as_utc,
    rows_affected,
)


class PostgresRemediationLedger(TenantBound):
    """One organisation's remediation outcomes and recurring problems."""

    async def record(self, outcome: RemediationOutcome) -> RemediationOutcome:
        """Store ``outcome``, replacing any earlier row for the same action."""
        values = _row(self.org_id, outcome)
        statement = insert(models.RemediationOutcomeRow).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "action_id"],
                set_={
                    key: statement.excluded[key]
                    for key in values
                    if key not in {"org_id", "action_id"}
                },
            )
        )
        return outcome

    async def get(self, action_id: str) -> RemediationOutcome | None:
        """Return the outcome recorded for ``action_id``, or ``None``."""
        found = await self.session.execute(
            select(models.RemediationOutcomeRow).where(
                models.RemediationOutcomeRow.org_id == self.org_id,
                models.RemediationOutcomeRow.action_id == action_id,
            )
        )
        row = found.scalar_one_or_none()
        return None if row is None else _outcome(row)

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: float = VERIFICATION_LEASE_SECONDS,
        limit: int = MAX_VERIFICATION_CLAIM_BATCH,
    ) -> tuple[RemediationOutcome, ...]:
        """Claim up to ``limit`` obligations due at ``now``, and return them."""
        check_claim_batch(limit)
        table = models.RemediationOutcomeRow
        due = await self.session.execute(
            select(table)
            .where(
                table.org_id == self.org_id,
                table.state != VerificationState.VERIFIED.value,
                table.due_at <= now,
                (table.lease_expires_at.is_(None)) | (table.lease_expires_at <= now),
            )
            .order_by(table.due_at, table.action_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        expires = now + timedelta(seconds=lease_seconds)
        claimed: list[RemediationOutcome] = []
        for row in due.scalars().all():
            row.state = VerificationState.CLAIMED.value
            row.attempts = row.attempts + 1
            row.lease_holder = worker_id
            row.lease_expires_at = expires
            claimed.append(_outcome(row))
        await self.session.flush()
        return tuple(claimed)

    async def history(self, query: EffectivenessQuery) -> tuple[RemediationOutcome, ...]:
        """Return the outcomes matching ``query``, most recently executed first."""
        limit = check_effectiveness_limit(query.limit)
        table = models.RemediationOutcomeRow
        found = await self.session.execute(
            _filtered(select(table), query, org_id=self.org_id)
            .order_by(table.executed_at.desc(), table.action_id.desc())
            .limit(limit)
        )
        return tuple(_outcome(row) for row in found.scalars().all())

    async def effectiveness(self, query: EffectivenessQuery) -> EffectivenessSummary:
        """Return the counts matching ``query``, over however much history there is."""
        table = models.RemediationOutcomeRow
        grouped = await self.session.execute(
            _filtered(
                select(table.state, table.verdict, func.count()).group_by(
                    table.state, table.verdict
                ),
                query,
                org_id=self.org_id,
            )
        )
        counts: dict[VerificationVerdict, int] = {}
        total = 0
        awaiting = 0
        for state, verdict, count in grouped.all():
            total += count
            if state == VerificationState.VERIFIED.value and verdict:
                counts[VerificationVerdict(verdict)] = (
                    counts.get(VerificationVerdict(verdict), 0) + count
                )
            else:
                awaiting += count

        latest = await self.session.execute(
            _filtered(select(table), query, org_id=self.org_id)
            .order_by(table.executed_at.desc(), table.action_id.desc())
            .limit(1)
        )
        newest = latest.scalar_one_or_none()
        return EffectivenessSummary(
            total=total,
            counts=counts,
            awaiting=awaiting,
            last_at=None if newest is None else as_utc(newest.executed_at),
            last_verdict=(
                None
                if newest is None or not newest.verdict
                else VerificationVerdict(newest.verdict)
            ),
        )

    async def upsert_problem(self, problem: RecurringProblem) -> RecurringProblem:
        """Store ``problem``, replacing any earlier record with the same id."""
        values = _problem_row(self.org_id, problem)
        statement = insert(models.RemediationProblemRow).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "problem_id"],
                set_={
                    key: statement.excluded[key]
                    for key in values
                    if key not in {"org_id", "problem_id"}
                },
            )
        )
        return problem

    async def open_problem_for(self, pattern_key: str) -> RecurringProblem | None:
        """Return the live problem for ``pattern_key``, or ``None``."""
        table = models.RemediationProblemRow
        found = await self.session.execute(
            select(table)
            .where(
                table.org_id == self.org_id,
                table.pattern_key == pattern_key,
                table.closed_at.is_(None),
            )
            .order_by(table.raised_at.desc(), table.problem_id.desc())
            .limit(1)
        )
        row = found.scalar_one_or_none()
        return None if row is None else _problem(row)

    async def problems(
        self,
        *,
        live_only: bool = True,
        limit: int = MAX_RECURRING_PROBLEM_PAGE_SIZE,
    ) -> tuple[RecurringProblem, ...]:
        """Return recurring problems, most recently raised first."""
        check_problem_limit(limit)
        table = models.RemediationProblemRow
        statement = select(table).where(table.org_id == self.org_id)
        if live_only:
            statement = statement.where(table.closed_at.is_(None))
        found = await self.session.execute(
            statement.order_by(table.raised_at.desc(), table.problem_id.desc()).limit(limit)
        )
        return tuple(_problem(row) for row in found.scalars().all())

    async def purge(self, *, before: datetime) -> int:
        """Delete verified outcomes executed before ``before`` and return how many."""
        table = models.RemediationOutcomeRow
        removed = await self.session.execute(
            delete(table).where(
                table.org_id == self.org_id,
                table.state == VerificationState.VERIFIED.value,
                table.executed_at < before,
            )
        )
        return rows_affected(removed)


def _filtered(statement: Any, query: EffectivenessQuery, *, org_id: str) -> Any:
    """Return ``statement`` narrowed by every filter ``query`` declares.

    One function for the listing and the aggregate, so a filter that means one
    thing in a count cannot come to mean another in the rows behind it.
    """
    table = models.RemediationOutcomeRow
    statement = statement.where(table.org_id == org_id)
    if query.resource_ids:
        statement = statement.where(table.resource_id.in_(query.resource_ids))
    if query.capabilities:
        statement = statement.where(table.capability.in_(query.capabilities))
    if query.condition_keys:
        statement = statement.where(table.condition_key.in_(query.condition_keys))
    if query.verdicts:
        statement = statement.where(table.verdict.in_([item.value for item in query.verdicts]))
    if query.states:
        statement = statement.where(table.state.in_([item.value for item in query.states]))
    if query.team_node_id is not None:
        statement = statement.where(table.team_node_id == query.team_node_id)
    if query.since is not None:
        statement = statement.where(table.executed_at >= query.since)
    if query.until is not None:
        statement = statement.where(table.executed_at <= query.until)
    return statement


def _row(org_id: str, outcome: RemediationOutcome) -> dict[str, Any]:
    """Return the column values one outcome is stored as."""
    return {
        "org_id": org_id,
        "action_id": outcome.action_id,
        "capability": outcome.capability,
        "resource_id": outcome.resource_id,
        "condition_key": outcome.condition_key,
        "team_node_id": outcome.team_node_id,
        "incident_id": outcome.incident_id,
        "run_id": outcome.run_id,
        "plan_id": outcome.plan_id,
        "executed_at": outcome.executed_at,
        "due_at": outcome.due_at,
        "settle_seconds": outcome.settle_seconds,
        "state": outcome.state.value,
        "verdict": "" if outcome.verdict is None else outcome.verdict.value,
        "signal_names": list(outcome.signal_names),
        "before_values": dict(outcome.before),
        "after_values": dict(outcome.after),
        "verified_at": outcome.verified_at,
        "detail": outcome.detail,
        "rollback": outcome.rollback.value,
        "rollback_detail": outcome.rollback_detail,
        "autonomous": outcome.autonomous,
        "undo": dict(outcome.undo),
        "attempts": outcome.attempts,
        "lease_holder": outcome.lease_holder,
        "lease_expires_at": outcome.lease_expires_at,
    }


def _outcome(row: models.RemediationOutcomeRow) -> RemediationOutcome:
    """Return the outcome one stored row describes."""
    return RemediationOutcome(
        action_id=row.action_id,
        capability=row.capability,
        resource_id=row.resource_id,
        condition_key=row.condition_key,
        team_node_id=row.team_node_id,
        incident_id=row.incident_id,
        run_id=row.run_id,
        plan_id=row.plan_id,
        executed_at=as_utc(row.executed_at) or row.executed_at,
        due_at=as_utc(row.due_at) or row.due_at,
        settle_seconds=row.settle_seconds,
        state=VerificationState(row.state),
        verdict=VerificationVerdict(row.verdict) if row.verdict else None,
        signal_names=as_tuple(row.signal_names),
        before={name: float(value) for name, value in dict(row.before_values).items()},
        after={name: float(value) for name, value in dict(row.after_values).items()},
        verified_at=as_utc(row.verified_at),
        detail=row.detail,
        rollback=RollbackDisposition(row.rollback),
        rollback_detail=row.rollback_detail,
        autonomous=row.autonomous,
        undo=dict(row.undo),
        attempts=row.attempts,
        lease_holder=row.lease_holder,
        lease_expires_at=as_utc(row.lease_expires_at),
    )


def _problem_row(org_id: str, problem: RecurringProblem) -> dict[str, Any]:
    """Return the column values one recurring problem is stored as."""
    return {
        "org_id": org_id,
        "problem_id": problem.problem_id,
        "pattern_key": problem.pattern_key,
        "capability": problem.capability,
        "resource_id": problem.resource_id,
        "title": problem.title,
        "summary": problem.summary,
        "raised_at": problem.raised_at,
        "occurrences": problem.occurrences,
        "window_seconds": problem.window_seconds,
        "action_ids": list(problem.action_ids),
        "incident_ids": list(problem.incident_ids),
        "team_node_id": problem.team_node_id,
        "suppresses_autonomy": problem.suppresses_autonomy,
        "closed_at": problem.closed_at,
        "close_reason": problem.close_reason,
        "closed_by": problem.closed_by,
    }


def _problem(row: models.RemediationProblemRow) -> RecurringProblem:
    """Return the recurring problem one stored row describes."""
    return RecurringProblem(
        problem_id=row.problem_id,
        pattern_key=row.pattern_key,
        capability=row.capability,
        resource_id=row.resource_id,
        title=row.title,
        summary=row.summary,
        raised_at=as_utc(row.raised_at) or row.raised_at,
        occurrences=row.occurrences,
        window_seconds=row.window_seconds,
        action_ids=as_tuple(row.action_ids),
        incident_ids=as_tuple(row.incident_ids),
        team_node_id=row.team_node_id,
        suppresses_autonomy=row.suppresses_autonomy,
        closed_at=as_utc(row.closed_at),
        close_reason=row.close_reason,
        closed_by=row.closed_by,
    )


__all__ = ["PostgresRemediationLedger"]
