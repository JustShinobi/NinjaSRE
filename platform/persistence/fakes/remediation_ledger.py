"""In-memory remediation outcomes and patterns, with the same guarantees as the real one.

Two dictionaries and the lookups the contract names. The one that matters is
``claim_due``: it stamps the lease as it selects, in the same pass, because a
select-then-stamp would let two workers both see one obligation before either
had written — which is the exact race the real backend's ``FOR UPDATE SKIP
LOCKED`` exists to prevent, and a fake that did not reproduce it would let the
contract suite pass against a backend that had the bug.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from config.constants.closed_loop import (
    MAX_RECURRING_PROBLEM_PAGE_SIZE,
    MAX_VERIFICATION_CLAIM_BATCH,
    VERIFICATION_LEASE_SECONDS,
)
from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    EffectivenessSummary,
    RecurringProblem,
    RemediationOutcome,
    VerificationState,
    check_claim_batch,
    check_effectiveness_limit,
    check_problem_limit,
    matches,
    summarise,
)


@dataclass(slots=True)
class FakeRemediationLedger:
    """One organisation's remediation outcomes and recurring problems."""

    org_id: str
    state: TenantState

    async def record(self, outcome: RemediationOutcome) -> RemediationOutcome:
        """Store ``outcome``, replacing any earlier row for the same action."""
        self.state.remediation_outcomes[outcome.action_id] = outcome
        return outcome

    async def get(self, action_id: str) -> RemediationOutcome | None:
        """Return the outcome recorded for ``action_id``, or ``None``."""
        return self.state.remediation_outcomes.get(action_id)

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
        expires = now + timedelta(seconds=lease_seconds)
        due = [
            row
            for row in self.state.remediation_outcomes.values()
            if row.state.is_open
            and row.due_at <= now
            and (row.lease_expires_at is None or row.lease_expires_at <= now)
        ]
        due.sort(key=lambda row: (row.due_at, row.action_id))

        claimed: list[RemediationOutcome] = []
        for row in due[:limit]:
            held = replace(
                row,
                state=VerificationState.CLAIMED,
                attempts=row.attempts + 1,
                lease_holder=worker_id,
                lease_expires_at=expires,
            )
            self.state.remediation_outcomes[held.action_id] = held
            claimed.append(held)
        return tuple(claimed)

    async def history(self, query: EffectivenessQuery) -> tuple[RemediationOutcome, ...]:
        """Return the outcomes matching ``query``, most recently executed first."""
        limit = check_effectiveness_limit(query.limit)
        found = [row for row in self.state.remediation_outcomes.values() if matches(row, query)]
        found.sort(key=lambda row: (row.executed_at, row.action_id), reverse=True)
        return tuple(found[:limit])

    async def effectiveness(self, query: EffectivenessQuery) -> EffectivenessSummary:
        """Return the counts matching ``query``, over however much history there is."""
        return summarise(
            tuple(row for row in self.state.remediation_outcomes.values() if matches(row, query))
        )

    async def upsert_problem(self, problem: RecurringProblem) -> RecurringProblem:
        """Store ``problem``, replacing any earlier record with the same id."""
        self.state.remediation_problems[problem.problem_id] = problem
        return problem

    async def open_problem_for(self, pattern_key: str) -> RecurringProblem | None:
        """Return the live problem for ``pattern_key``, or ``None``."""
        live = [
            problem
            for problem in self.state.remediation_problems.values()
            if problem.pattern_key == pattern_key and problem.is_live
        ]
        if not live:
            return None
        return max(live, key=lambda problem: (problem.raised_at, problem.problem_id))

    async def problems(
        self,
        *,
        live_only: bool = True,
        limit: int = MAX_RECURRING_PROBLEM_PAGE_SIZE,
    ) -> tuple[RecurringProblem, ...]:
        """Return recurring problems, most recently raised first."""
        check_problem_limit(limit)
        found = [
            problem
            for problem in self.state.remediation_problems.values()
            if problem.is_live or not live_only
        ]
        found.sort(key=lambda problem: (problem.raised_at, problem.problem_id), reverse=True)
        return tuple(found[:limit])

    async def purge(self, *, before: datetime) -> int:
        """Delete verified outcomes executed before ``before`` and return how many."""
        expired = [
            action_id
            for action_id, row in self.state.remediation_outcomes.items()
            if row.state is VerificationState.VERIFIED and row.executed_at < before
        ]
        for action_id in expired:
            del self.state.remediation_outcomes[action_id]
        return len(expired)


__all__ = ["FakeRemediationLedger"]
