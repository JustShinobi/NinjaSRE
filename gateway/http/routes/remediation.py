"""What the deployment changed, whether it worked, and the two things a person does.

Six routes over the remediation ledger. The shapes below are decisions rather
than conveniences, and two of them are worth stating.

**An action awaiting verification says so, and never says it succeeded.** The
listing and the detail both carry ``awaiting_verification`` as its own field
rather than leaving a caller to infer it from a missing verdict. A console that
had to infer it would render "succeeded" for the five minutes between the change
and the check, which is the window in which an operator is actually looking.

**Effectiveness is counts, and the sentence beside them.** The counts are what a
screen renders and the sentence is what a proposal reads, and both come from one
place — two renderings of one history is two places for them to disagree.

Clearing a suspension takes a reason and refuses without one at the schema. The
whole of that control is that a person looked at a resource nobody knows the
state of, and a clearing with no reason records that nobody did.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from config.constants.closed_loop import (
    MAX_EFFECTIVENESS_PAGE_SIZE,
    MAX_RECURRING_PROBLEM_PAGE_SIZE,
)
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.persistence.errors import BoundExceeded
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    RecurringProblem,
    RemediationOutcome,
)
from platform.remediation.errors import UnknownRecurringProblem
from platform.remediation.history import EffectivenessHistory
from platform.remediation.recurrence import RecurrenceWatch
from platform.remediation.suspension import AutonomySuspensions, Suspension

router = APIRouter(prefix="/v1", tags=["remediation"])

#: How many outcomes a listing returns when the caller does not say. A screen's
#: worth: an operator opening the page wants what the deployment did today.
DEFAULT_OUTCOME_PAGE = 25


class OutcomeView(BaseModel):
    """One remediation, and what became of it."""

    action_id: str
    capability: str
    resource_id: str
    condition_key: str = ""
    incident_id: str = ""
    run_id: str = ""
    executed_at: datetime
    due_at: datetime
    settle_seconds: int = 0
    #: Never inferred from a missing verdict. See the module docstring.
    awaiting_verification: bool = True
    verdict: str | None = None
    verified_at: datetime | None = None
    signals: list[str] = Field(default_factory=list)
    before: dict[str, float] = Field(default_factory=dict)
    after: dict[str, float] = Field(default_factory=dict)
    rollback: str = "not_required"
    rollback_detail: str = ""
    autonomous: bool = False
    attempts: int = 0
    detail: str = ""


class OutcomeListView(BaseModel):
    outcomes: list[OutcomeView]
    #: How many of these are still settling. On the listing because "why does
    #: nothing say whether it worked" is asked here.
    awaiting: int = 0


class EffectivenessView(BaseModel):
    """How often one thing has worked, as counts and as the sentence."""

    capability: str = ""
    resource_id: str = ""
    condition_key: str = ""
    total: int = 0
    verified: int = 0
    awaiting: int = 0
    success_ratio: float = 0.0
    counts: dict[str, int] = Field(default_factory=dict)
    last_at: datetime | None = None
    last_verdict: str | None = None
    known: bool = False
    discouraged: bool = False
    summary: str = ""


class ProblemView(BaseModel):
    """One recurring problem: a pattern, closed by a change."""

    problem_id: str
    pattern_key: str
    capability: str
    resource_id: str
    title: str
    summary: str
    raised_at: datetime
    occurrences: int
    window_seconds: int
    action_ids: list[str] = Field(default_factory=list)
    incident_ids: list[str] = Field(default_factory=list)
    suppresses_autonomy: bool = True
    live: bool = True
    closed_at: datetime | None = None
    close_reason: str = ""
    closed_by: str = ""


class ProblemListView(BaseModel):
    problems: list[ProblemView]


class SuspensionView(BaseModel):
    """One resource the deployment has stopped acting on unattended."""

    resource_id: str
    since: datetime
    reason: str
    action_id: str = ""
    live: bool = True
    cleared_at: datetime | None = None
    cleared_by: str = ""
    clear_reason: str = ""


class SuspensionListView(BaseModel):
    suspensions: list[SuspensionView]


class ClearRequest(BaseModel):
    """What the person who looked at the resource found.

    Required, and refused at the schema. A suspension is raised because nobody
    knows what state a resource is in; a clearing with no reason records that
    nobody found out.
    """

    reason: str = Field(min_length=1)


class CloseProblemRequest(BaseModel):
    """The change that closed this pattern.

    Required for the reason ``RecurringProblem`` enforces it: a recurring
    problem is closed by a change, and a close that does not say which is a
    record that the problem stopped being displayed.
    """

    change: str = Field(min_length=1)


def _outcome(row: RemediationOutcome) -> OutcomeView:
    return OutcomeView(
        action_id=row.action_id,
        capability=row.capability,
        resource_id=row.resource_id,
        condition_key=row.condition_key,
        incident_id=row.incident_id,
        run_id=row.run_id,
        executed_at=row.executed_at,
        due_at=row.due_at,
        settle_seconds=row.settle_seconds,
        awaiting_verification=row.awaiting_verification,
        verdict=row.verdict.value if row.verdict is not None else None,
        verified_at=row.verified_at,
        signals=list(row.signal_names),
        before=dict(row.before),
        after=dict(row.after),
        rollback=row.rollback.value,
        rollback_detail=row.rollback_detail,
        autonomous=row.autonomous,
        attempts=row.attempts,
        detail=row.detail,
    )


def _problem(problem: RecurringProblem) -> ProblemView:
    return ProblemView(
        problem_id=problem.problem_id,
        pattern_key=problem.pattern_key,
        capability=problem.capability,
        resource_id=problem.resource_id,
        title=problem.title,
        summary=problem.summary,
        raised_at=problem.raised_at,
        occurrences=problem.occurrences,
        window_seconds=problem.window_seconds,
        action_ids=list(problem.action_ids),
        incident_ids=list(problem.incident_ids),
        suppresses_autonomy=problem.suppresses_autonomy,
        live=problem.is_live,
        closed_at=problem.closed_at,
        close_reason=problem.close_reason,
        closed_by=problem.closed_by,
    )


def _suspension(suspension: Suspension) -> SuspensionView:
    return SuspensionView(
        resource_id=suspension.resource_id,
        since=suspension.since,
        reason=suspension.reason,
        action_id=suspension.action_id,
        live=suspension.is_live,
        cleared_at=suspension.cleared_at,
        cleared_by=suspension.cleared_by,
        clear_reason=suspension.clear_reason,
    )


@router.get("/remediations", response_model=OutcomeListView)
async def list_remediations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    resource: str = "",
    capability: str = "",
    condition: str = "",
    limit: int = DEFAULT_OUTCOME_PAGE,
) -> OutcomeListView:
    """Return what the deployment has changed, most recent first."""
    try:
        async with state.gateway.begin(auth.scope) as unit:
            rows = await EffectivenessHistory(ledger=unit.remediation).recent(
                resource_id=resource,
                capability=capability,
                condition_key=condition,
                limit=limit,
            )
    except BoundExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"a remediation listing is bounded at {MAX_EFFECTIVENESS_PAGE_SIZE}; {exceeded}"
            ),
        ) from exceeded

    return OutcomeListView(
        outcomes=[_outcome(row) for row in rows],
        awaiting=len([row for row in rows if row.awaiting_verification]),
    )


@router.get("/remediations/effectiveness/summary", response_model=EffectivenessView)
async def effectiveness(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    resource: str = "",
    capability: str = "",
    condition: str = "",
) -> EffectivenessView:
    """Return how often this has worked, sliced by whatever was named.

    With a capability *and* a resource this is the question a proposal asks, and
    the answer carries the sentence a reviewer reads. With one of them it is the
    aggregate a screen renders.
    """
    async with state.gateway.begin(auth.scope) as unit:
        history = EffectivenessHistory(ledger=unit.remediation)
        if capability and resource:
            prior = await history.prior(capability, resource, condition_key=condition)
            return EffectivenessView(**prior.to_record())
        summary = await unit.remediation.effectiveness(
            EffectivenessQuery(
                resource_ids=(resource,) if resource else (),
                capabilities=(capability,) if capability else (),
                condition_keys=(condition,) if condition else (),
            )
        )

    return EffectivenessView(
        capability=capability,
        resource_id=resource,
        condition_key=condition,
        total=summary.total,
        verified=summary.verified,
        awaiting=summary.awaiting,
        success_ratio=round(summary.success_ratio, 4),
        counts={verdict.value: count for verdict, count in sorted(summary.counts.items())},
        last_at=summary.last_at,
        last_verdict=summary.last_verdict.value if summary.last_verdict else None,
        known=summary.verified > 0,
    )


@router.get("/remediations/problems/recurring", response_model=ProblemListView)
async def recurring_problems(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    live: bool = Query(default=True),
    limit: int = MAX_RECURRING_PROBLEM_PAGE_SIZE,
) -> ProblemListView:
    """Return the patterns the deployment has raised, most recent first."""
    try:
        async with state.gateway.begin(auth.scope) as unit:
            problems = await unit.remediation.problems(live_only=live, limit=limit)
    except BoundExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exceeded),
        ) from exceeded
    return ProblemListView(problems=[_problem(problem) for problem in problems])


@router.post("/remediations/problems/{problem_id}/close", response_model=ProblemView)
async def close_recurring_problem(
    problem_id: str,
    request: CloseProblemRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ProblemView:
    """Close a pattern, naming the change that closed it, and lift its suppression."""
    async with state.gateway.begin(auth.scope) as unit:
        try:
            closed = await RecurrenceWatch(ledger=unit.remediation).close(
                problem_id,
                principal_id=auth.principal_id,
                change=request.change,
                at=datetime.now(UTC),
            )
        except UnknownRecurringProblem as missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no recurring problem {problem_id!r} in this organisation",
            ) from missing
    return _problem(closed)


@router.get("/remediations/suspensions", response_model=SuspensionListView)
async def list_suspensions(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    live: bool = Query(default=True),
) -> SuspensionListView:
    """Return the resources the deployment has stopped acting on unattended."""
    async with state.gateway.begin(auth.scope) as unit:
        found = await AutonomySuspensions(audit=unit.audit).all(live_only=live)
    return SuspensionListView(suspensions=[_suspension(item) for item in found])


@router.post("/remediations/suspensions/{resource_id}/clear", response_model=SuspensionView)
async def clear_suspension(
    resource_id: str,
    request: ClearRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SuspensionView:
    """Let autonomy resume on a resource, recording who looked and what they found."""
    async with state.gateway.begin(auth.scope) as unit:
        cleared = await AutonomySuspensions(audit=unit.audit).clear(
            resource_id,
            principal_id=auth.principal_id,
            reason=request.reason,
            at=datetime.now(UTC),
        )
    if cleared is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"autonomous action on {resource_id!r} is not suspended",
        )
    return _suspension(cleared)


# Declared after the literal paths. FastAPI matches in registration order, so a
# route with a path parameter declared first would swallow
# ``/remediations/suspensions`` and answer it as an action nobody can find.
@router.get("/remediations/{action_id}", response_model=OutcomeView)
async def remediation_detail(
    action_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> OutcomeView:
    """Return one remediation, and whether anybody has found out if it worked."""
    async with state.gateway.begin(auth.scope) as unit:
        found = await unit.remediation.get(action_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no remediation {action_id!r} in this organisation",
        )
    return _outcome(found)


__all__ = ["router"]
