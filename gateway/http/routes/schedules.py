"""Scheduled investigations: create, list, read, update, delete, enable, disable, preview.

A thin wrapper over ``platform.scheduler.service.ScheduleService``, which
already does everything this route needs — validating the cron expression
before storing it, and computing the first due time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.runs import DEFAULT_SCHEDULE_TIMEZONE, SCHEDULE_PREVIEW_FIRING_COUNT
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.state import GatewayState
from platform.persistence.errors import RecordNotFound
from platform.scheduler.cron import CronError, CronExpression
from platform.scheduler.models import MisfirePolicy, Schedule
from platform.scheduler.service import ScheduleService

router = APIRouter(prefix="/v1/schedules", tags=["schedules"])


class ScheduleView(BaseModel):
    job_id: str
    name: str
    team_node_id: str
    cron: str
    objective: str
    timezone: str
    enabled: bool
    next_run_at: str | None = None


class CreateScheduleRequest(BaseModel):
    job_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    misfire: str = MisfirePolicy.RUN_ONCE.value


class UpdateScheduleRequest(BaseModel):
    cron: str = Field(min_length=1)
    timezone: str | None = None


class SchedulePreviewRequest(BaseModel):
    cron: str = Field(min_length=1)
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE


class ScheduleFiringView(BaseModel):
    """One instant a cron expression would fire at, resolved and nothing else."""

    at: str
    #: Whether daylight saving moved this firing — see ``FireTime`` for why
    #: that is the answer rather than skipping or doubling it.
    shifted: bool = False


class SchedulePreviewView(BaseModel):
    firings: list[ScheduleFiringView]


def _view(schedule: Schedule) -> ScheduleView:
    return ScheduleView(
        job_id=schedule.job_id,
        name=schedule.name,
        team_node_id=schedule.team_node_id,
        cron=schedule.cron,
        objective=schedule.objective,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        next_run_at=schedule.next_run_at.isoformat() if schedule.next_run_at else None,
    )


@router.get("", response_model=list[ScheduleView])
async def list_schedules(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> list[ScheduleView]:
    """Return this team's scheduled investigations."""
    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        schedules = await service.list(team_node_id=auth.team_node_id or None)
    return [_view(schedule) for schedule in schedules]


@router.post("", response_model=ScheduleView, status_code=201)
async def create_schedule(
    body: CreateScheduleRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ScheduleView:
    """Create a scheduled investigation, validating the cron expression first."""
    try:
        misfire = MisfirePolicy(body.misfire)
    except ValueError as error:
        raise bad_request(f"{body.misfire!r} is not a misfire policy") from error

    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        try:
            schedule = await service.create(
                job_id=body.job_id,
                name=body.name,
                team_node_id=auth.team_node_id,
                principal_id=auth.principal_id,
                cron=body.cron,
                objective=body.objective,
                timezone=body.timezone,
                misfire=misfire,
            )
        except CronError as error:
            raise bad_request(str(error)) from error
    return _view(schedule)


@router.post("/preview", response_model=SchedulePreviewView)
async def preview_schedule(
    body: SchedulePreviewRequest,
    auth: AuthenticatedRequest = Depends(authorized),
) -> SchedulePreviewView:
    """Return what ``cron`` would fire, storing nothing.

    Parsed through the same ``CronExpression`` the write path validates
    with — a form calling this and a form calling ``create`` can never
    disagree about what an expression means, because there is one
    implementation of cron in this deployment rather than a console-side
    second opinion beside a server-side first one. A refused expression is
    refused here exactly as ``create`` would refuse it, before anything
    would have been stored.
    """
    del auth  # the permission check is the whole reason this parameter exists
    try:
        expression = CronExpression.parse(body.cron, timezone=body.timezone)
    except CronError as error:
        raise bad_request(str(error)) from error

    firings: list[ScheduleFiringView] = []
    moment = datetime.now(UTC)
    for _ in range(SCHEDULE_PREVIEW_FIRING_COUNT):
        try:
            fire = expression.next_after(moment)
        except CronError as error:
            raise bad_request(str(error)) from error
        firings.append(ScheduleFiringView(at=fire.at.isoformat(), shifted=fire.shifted))
        moment = fire.at

    return SchedulePreviewView(firings=firings)


@router.get("/{job_id}", response_model=ScheduleView)
async def get_schedule(
    job_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ScheduleView:
    """Return one schedule."""
    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        schedule = await service.get(job_id)
    if schedule is None or (auth.team_node_id and schedule.team_node_id != auth.team_node_id):
        raise not_found(f"no schedule {job_id!r}")
    return _view(schedule)


@router.put("/{job_id}", response_model=ScheduleView)
async def update_schedule(
    job_id: str,
    body: UpdateScheduleRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ScheduleView:
    """Change a schedule's cron expression."""
    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        existing = await service.get(job_id)
        if existing is None or (auth.team_node_id and existing.team_node_id != auth.team_node_id):
            raise not_found(f"no schedule {job_id!r}")
        try:
            schedule = await service.update_expression(
                job_id, cron=body.cron, timezone=body.timezone
            )
        except CronError as error:
            raise bad_request(str(error)) from error
    return _view(schedule)


@router.delete("/{job_id}", status_code=204)
async def delete_schedule(
    job_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> None:
    """Remove a scheduled investigation."""
    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        existing = await service.get(job_id)
        if existing is None or (auth.team_node_id and existing.team_node_id != auth.team_node_id):
            raise not_found(f"no schedule {job_id!r}")
        await service.delete(job_id)


@router.post("/{job_id}/enable", response_model=ScheduleView)
async def enable_schedule(
    job_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ScheduleView:
    """Enable a schedule."""
    return await _set_enabled(job_id, True, state, auth)


@router.post("/{job_id}/disable", response_model=ScheduleView)
async def disable_schedule(
    job_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ScheduleView:
    """Disable a schedule."""
    return await _set_enabled(job_id, False, state, auth)


async def _set_enabled(
    job_id: str, enabled: bool, state: GatewayState, auth: AuthenticatedRequest
) -> ScheduleView:
    async with state.gateway.begin(auth.scope) as uow:
        service = ScheduleService(store=uow.schedules)
        existing = await service.get(job_id)
        if existing is None or (auth.team_node_id and existing.team_node_id != auth.team_node_id):
            raise not_found(f"no schedule {job_id!r}")
        try:
            schedule = await service.set_enabled(job_id, enabled=enabled)
        except RecordNotFound as error:
            raise not_found(str(error)) from error
    return _view(schedule)


__all__ = ["router"]
