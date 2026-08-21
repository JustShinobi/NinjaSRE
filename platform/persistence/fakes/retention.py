"""In-memory retention sweeping, across every tenant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from platform.persistence.errors import RetentionExempt
from platform.persistence.fakes.estate_repository import purge_estate_history
from platform.persistence.fakes.state import State, TenantState
from platform.persistence.fakes.transit_ledger import purge_transit
from platform.persistence.ports.retention import DataClass, PurgeReport, RetentionPolicy

#: A record with no timestamp is treated as new rather than ancient. Retention
#: deletes things; the failure mode that costs an operator their evidence is
#: deleting too much, so an undated record survives until somebody dates it.
_UNDATED = datetime.max.replace(tzinfo=UTC)


@dataclass(slots=True)
class FakeRetentionSweeper:
    """Applies retention policies to every organisation in the store."""

    state: State

    async def purge(self, policy: RetentionPolicy, *, now: datetime) -> PurgeReport:
        """Delete records older than ``policy``'s cutoff and report the count."""
        if policy.data_class.is_exempt:
            raise RetentionExempt(policy.data_class.value)

        cutoff = policy.cutoff(now)
        if cutoff is None:
            return PurgeReport(data_class=policy.data_class, deleted=0, cutoff=None)

        deleted = sum(
            _purge_tenant(tenant, policy.data_class, cutoff)
            for tenant in self.state.tenants.values()
        )
        return PurgeReport(data_class=policy.data_class, deleted=deleted, cutoff=cutoff)

    async def purge_all(
        self,
        policies: tuple[RetentionPolicy, ...],
        *,
        now: datetime,
    ) -> tuple[PurgeReport, ...]:
        """Apply every policy and return one report each, in the order given."""
        reports: list[PurgeReport] = []
        for policy in policies:
            reports.append(await self.purge(policy, now=now))
        return tuple(reports)


def _purge_tenant(tenant: TenantState, data_class: DataClass, cutoff: datetime) -> int:
    """Delete one tenant's expired records of one class, and return the count."""
    match data_class:
        case DataClass.RUN_TRACES:
            return _purge_runs(tenant, cutoff)
        case DataClass.SESSIONS:
            expired = [
                key
                for key, record in tenant.sessions.items()
                if (record.updated_at or _UNDATED) < cutoff
            ]
            for key in expired:
                del tenant.sessions[key]
            return len(expired)
        case DataClass.EPISODES:
            expired = [
                key
                for key, episode in tenant.episodes.items()
                if (episode.occurred_at or _UNDATED) < cutoff
            ]
            for key in expired:
                del tenant.episodes[key]
            return len(expired)
        case DataClass.KNOWLEDGE:
            return _purge_documents(tenant, cutoff)
        case DataClass.ESTATE_HISTORY:
            return purge_estate_history(tenant, cutoff)
        case DataClass.TRANSIT:
            return purge_transit(tenant, cutoff)
        case DataClass.AUDIT:  # pragma: no cover — refused before reaching here
            raise RetentionExempt(data_class.value)


def _purge_runs(tenant: TenantState, cutoff: datetime) -> int:
    """Delete expired runs and everything hanging off them.

    Turns, tool calls, evidence, and the event log go with their run. A trace
    missing its evidence is not a smaller trace, it is a misleading one — it
    shows what the model said with no record of what the system observed.
    """
    expired = {
        run_id
        for run_id, run in tenant.runs.items()
        if (run.finished_at or run.started_at or _UNDATED) < cutoff
    }
    if not expired:
        return 0

    for run_id in expired:
        del tenant.runs[run_id]
    for key in [k for k, turn in tenant.turns.items() if turn.run_id in expired]:
        del tenant.turns[key]
    for key in [k for k, call in tenant.tool_calls.items() if call.run_id in expired]:
        del tenant.tool_calls[key]
    for key in [k for k, item in tenant.evidence.items() if item.run_id in expired]:
        del tenant.evidence[key]
    for key in [k for k, event in tenant.trace_events.items() if event.run_id in expired]:
        del tenant.trace_events[key]
    return len(expired)


def _purge_documents(tenant: TenantState, cutoff: datetime) -> int:
    """Delete expired knowledge documents and their chunks."""
    expired = {
        document_id
        for document_id, document in tenant.documents.items()
        if (document.updated_at or _UNDATED) < cutoff
    }
    for document_id in expired:
        del tenant.documents[document_id]
    for key in [k for k, chunk in tenant.chunks.items() if chunk.document_id in expired]:
        del tenant.chunks[key]
    return len(expired)


__all__ = ["FakeRetentionSweeper"]
