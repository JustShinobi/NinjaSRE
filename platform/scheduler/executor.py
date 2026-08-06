"""Running a claimed job: one firing, one run, the current configuration.

Three properties, and each is a thing a scheduler gets wrong in a way that is
invisible for months.

**Configuration is resolved at execution time, not at configuration time.** A
schedule created in March and running in September uses September's model,
September's prompts, September's enabled capabilities. Capturing them at
creation would mean a team that changed its configuration had one job still
quietly running the old one, and nothing in the schedule would say so.

**The run id is derived from the job and the firing.** Two replicas that both
decided a firing was theirs derive the same id, and the second ``start_run``
fails on a duplicate rather than producing a second investigation. The claim
usually makes this unreachable; it is here for the case where the claim was
wrong, which is the case a lease-based design has to have an answer for.

**A scheduled run is an ordinary run.** Same records, same trace, same event
log, same history — differing only in the trigger it carries and the principal
it attributes to. Anything that made scheduled runs a separate kind of thing
would mean everything downstream had two cases to handle, and the second one
would be the one nobody tested.

The pipeline itself is a protocol rather than an import: this is tier 3 and the
investigation pipeline is where the runtime lives, so a composition root hands
one over. That also makes "what did the scheduler do" testable without standing
up a model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.runs import TRIGGER_SCHEDULE
from platform.observability.logging import get_logger
from platform.persistence.errors import DuplicateRecord
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.schedule_store import JobOutcome
from platform.runs.recorder import RunRecorder
from platform.scheduler.claiming import fire_key
from platform.scheduler.concurrency import ConcurrencyLimits
from platform.scheduler.models import Schedule

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ScheduledRunRequest:
    """What the pipeline is asked to investigate, and on whose behalf."""

    run_id: str
    job_id: str
    team_node_id: str
    principal_id: str
    objective: str
    fire_time: datetime
    context: Mapping[str, Any] = field(default_factory=dict)
    settings: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ScheduledInvestigation(Protocol):
    """What the scheduler needs from the investigation pipeline.

    One method, because a scheduler that could configure an investigation would
    be a second place investigations are configured. It hands over what it knows
    and reads a summary back.
    """

    async def investigate(self, request: ScheduledRunRequest) -> str:
        """Run the investigation ``request`` describes and return its summary."""


@runtime_checkable
class EffectiveSettings(Protocol):
    """Resolves a team's current effective configuration.

    A protocol for the same tier reason as above, and because a scheduler with
    no resolver still works — it runs with whatever defaults the pipeline holds,
    which is what a single-team deployment looks like.
    """

    async def resolve(self, team_node_id: str) -> Mapping[str, Any]:
        """Return the configuration in force for ``team_node_id`` right now."""


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """What one firing of one job produced."""

    job_id: str
    fire_time: datetime
    outcome: JobOutcome
    run: AgentRun | None = None
    summary: str = ""
    failure: str | None = None
    duplicate: bool = False

    @property
    def ran(self) -> bool:
        """Return whether an investigation actually happened."""
        return self.run is not None and not self.duplicate


@dataclass(slots=True)
class JobExecutor:
    """Runs one claimed firing through the investigation pipeline."""

    recorder: RunRecorder
    pipeline: ScheduledInvestigation
    settings: EffectiveSettings | None = None
    limits: ConcurrencyLimits = field(default_factory=ConcurrencyLimits)
    clock: Callable[[], datetime] = _utc_now

    async def execute(self, schedule: Schedule, *, fire_time: datetime) -> ExecutionResult:
        """Run ``schedule``'s ``fire_time`` and report what happened.

        Never raises for a failing investigation. A scheduler that propagated
        one would drop the release of the claim with it, and the job would then
        be blocked until the lease expired — turning one failed run into five
        minutes of a schedule not existing.
        """
        run_id = fire_key(schedule.job_id, fire_time)

        async with self.limits.permit(schedule.team_node_id):
            try:
                run = await self.recorder.start_run(
                    trigger=TRIGGER_SCHEDULE,
                    principal_id=schedule.principal_id,
                    team_node_id=schedule.team_node_id,
                    run_id=run_id,
                    job_id=schedule.job_id,
                )
            except DuplicateRecord:
                # Another replica got this firing. Not an error and not a
                # failure of the job: exactly the outcome the key exists for.
                logger.info("scheduler.firing_already_run", job_id=schedule.job_id, run_id=run_id)
                return ExecutionResult(
                    job_id=schedule.job_id,
                    fire_time=fire_time,
                    outcome=JobOutcome.SUCCEEDED,
                    duplicate=True,
                )

            return await self._investigate(schedule, run=run, fire_time=fire_time)

    async def _investigate(
        self, schedule: Schedule, *, run: AgentRun, fire_time: datetime
    ) -> ExecutionResult:
        """Drive the pipeline and close the run whichever way it ends."""
        # Resolved here rather than held on the schedule: a job created in March
        # and running in September uses September's configuration.
        settings = await self.settings.resolve(schedule.team_node_id) if self.settings else {}
        request = ScheduledRunRequest(
            run_id=run.run_id,
            job_id=schedule.job_id,
            team_node_id=schedule.team_node_id,
            principal_id=schedule.principal_id,
            objective=schedule.objective,
            fire_time=fire_time,
            context=dict(schedule.context),
            settings=settings,
        )

        try:
            summary = await self.pipeline.investigate(request)
        except Exception as failure:  # noqa: BLE001 — recorded, then reported
            await self.recorder.complete_run(
                run.run_id, status=RunStatus.FAILED, summary=str(failure)
            )
            logger.error(
                "scheduler.run_failed",
                job_id=schedule.job_id,
                run_id=run.run_id,
                error=type(failure).__name__,
            )
            return ExecutionResult(
                job_id=schedule.job_id,
                fire_time=fire_time,
                outcome=JobOutcome.FAILED,
                run=run,
                failure=str(failure),
            )

        closed = await self.recorder.complete_run(
            run.run_id, status=RunStatus.COMPLETED, summary=summary
        )
        return ExecutionResult(
            job_id=schedule.job_id,
            fire_time=fire_time,
            outcome=JobOutcome.SUCCEEDED,
            run=closed,
            summary=summary,
        )


__all__ = [
    "EffectiveSettings",
    "ExecutionResult",
    "JobExecutor",
    "ScheduledInvestigation",
    "ScheduledRunRequest",
]
