"""Reclaiming a trace without erasing the fact that the investigation happened.

The persistence layer's own sweeper deletes runs whole, which is right for a
deployment that wants the storage back and does not want the history. This is
the other half of the same requirement and the one an operator actually
configures: strip the *detail* — turns, calls, evidence, the event log — and
keep the run row, its status, its timings, and the summary of what it concluded.

The distinction is the requirement. An investigation whose summary survived is
one an operator can still find, cite in a post-mortem, and count in a report; a
run whose row was deleted is one that, as far as anything downstream can tell,
never happened. The audit trail is untouched by either path — it has no
deletion method at all — so a stripped trace still has a record of who ran it
and what it was allowed to do.

Per data class, because the classes have genuinely different lifetimes: a run's
detail is evidence for one incident, and the summary is a row in the history a
team looks at a year later.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from config.constants.persistence import MAX_QUERY_PAGE_SIZE, RETENTION_DAYS_RUN_TRACES
from platform.observability.logging import get_logger
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus, RunTraceStore

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TraceRetentionReport:
    """What one retention pass over one tenant's traces actually did."""

    cutoff: datetime | None = None
    runs_stripped: int = 0
    records_removed: int = 0
    runs_preserved: int = 0

    @property
    def happened(self) -> bool:
        """Return whether the pass removed anything."""
        return bool(self.runs_stripped)


@dataclass(slots=True)
class TraceRetention:
    """Strips expired trace detail from one tenant, preserving the runs.

    Holds a store rather than a gateway for the same reason the recorder does:
    the store came out of a unit of work, so a pass that fails part-way rolls
    back rather than leaving half the traces stripped.
    """

    store: RunTraceStore
    retention_days: int = RETENTION_DAYS_RUN_TRACES
    clock: Callable[[], datetime] = _utc_now
    #: Statuses whose detail is kept past the window. A run still going is not
    #: old, whatever its start time says, and stripping one mid-flight would
    #: delete the trace the recorder is in the middle of writing.
    keep_while: frozenset[RunStatus] = field(
        default_factory=lambda: frozenset({RunStatus.RUNNING, RunStatus.SUSPENDED})
    )

    def cutoff(self, now: datetime | None = None) -> datetime | None:
        """Return the instant before which trace detail may be removed."""
        if self.retention_days < 1:
            return None
        return (now or self.clock()) - timedelta(days=self.retention_days)

    async def sweep(
        self,
        *,
        now: datetime | None = None,
        limit: int = MAX_QUERY_PAGE_SIZE,
    ) -> TraceRetentionReport:
        """Strip every expired run's detail and report what went.

        ``limit`` bounds one pass rather than the whole backlog: a deployment
        that has not swept for a year should reclaim its storage over several
        passes instead of holding one transaction open across all of it.
        """
        moment = now or self.clock()
        cutoff = self.cutoff(moment)
        if cutoff is None:
            return TraceRetentionReport(cutoff=None)

        expired = await self._expired(cutoff, limit=limit)
        removed = 0
        for run in expired:
            removed += await self.store.strip_trace(run.run_id)

        report = TraceRetentionReport(
            cutoff=cutoff,
            runs_stripped=len(expired),
            records_removed=removed,
            runs_preserved=len(expired),
        )
        if report.happened:
            logger.info(
                "runs.retention_swept",
                cutoff=cutoff.isoformat(),
                runs=report.runs_stripped,
                records=report.records_removed,
            )
        return report

    async def _expired(self, cutoff: datetime, *, limit: int) -> Sequence[AgentRun]:
        """Return the runs whose detail is past the window.

        Filtered on ``finished_at`` when there is one and on ``started_at``
        otherwise, and never on an undated run: retention deletes things, and
        the failure that costs an operator their evidence is deleting too much.
        """
        candidates = await self.store.list_runs(until=cutoff, limit=limit)
        return [run for run in candidates if self._is_expired(run, cutoff)]

    def _is_expired(self, run: AgentRun, cutoff: datetime) -> bool:
        """Return whether ``run``'s detail may be removed."""
        if run.status in self.keep_while:
            return False
        dated = run.finished_at or run.started_at
        return dated is not None and dated < cutoff


__all__ = ["TraceRetention", "TraceRetentionReport"]
