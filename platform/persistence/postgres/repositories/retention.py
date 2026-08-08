"""Retention sweeping over PostgreSQL, across every tenant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform.persistence.errors import RetentionExempt
from platform.persistence.ports.retention import DataClass, PurgeReport, RetentionPolicy
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import rows_affected


@dataclass(slots=True)
class PostgresRetentionSweeper:
    """Applies retention policies to every organisation in the store."""

    session: AsyncSession

    async def purge(self, policy: RetentionPolicy, *, now: datetime) -> PurgeReport:
        """Delete records older than ``policy``'s cutoff and report the count."""
        if policy.data_class.is_exempt:
            raise RetentionExempt(policy.data_class.value)

        cutoff = policy.cutoff(now)
        if cutoff is None:
            return PurgeReport(data_class=policy.data_class, deleted=0, cutoff=None)

        deleted = await self._purge(policy.data_class, cutoff)
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

    async def _purge(self, data_class: DataClass, cutoff: datetime) -> int:
        """Delete one class's expired records and return how many rows went."""
        match data_class:
            case DataClass.RUN_TRACES:
                # Turns, tool calls, and evidence go by cascade. A trace missing
                # its evidence is not a smaller trace, it is a misleading one:
                # what the model said, with no record of what was observed.
                #
                # An undated record is treated as new rather than ancient.
                # Retention deletes things, and the failure that costs an
                # operator their evidence is deleting too much.
                statement = delete(models.AgentRun).where(
                    or_(
                        models.AgentRun.finished_at < cutoff,
                        (models.AgentRun.finished_at.is_(None))
                        & (models.AgentRun.started_at < cutoff),
                    )
                )
            case DataClass.SESSIONS:
                statement = delete(models.Session).where(models.Session.updated_at < cutoff)
            case DataClass.EPISODES:
                statement = delete(models.Episode).where(models.Episode.occurred_at < cutoff)
            case DataClass.KNOWLEDGE:
                statement = delete(models.KnowledgeDocument).where(
                    models.KnowledgeDocument.updated_at < cutoff
                )
            case DataClass.ESTATE_HISTORY:
                # Two tables, so this class returns early rather than falling
                # through to the single-statement path below. The resources
                # themselves are deliberately not swept: an absent resource *is*
                # the record that something was removed.
                return await self._purge_estate_history(cutoff)
            case DataClass.AUDIT:  # pragma: no cover — refused before reaching here
                raise RetentionExempt(data_class.value)

        result = await self.session.execute(statement)
        await self.session.flush()
        return rows_affected(result)

    async def _purge_estate_history(self, cutoff: datetime) -> int:
        """Delete expired health transitions and resource references."""
        transitions = await self.session.execute(
            delete(models.HealthTransitionRow).where(
                models.HealthTransitionRow.occurred_at < cutoff
            )
        )
        references = await self.session.execute(
            delete(models.ResourceReferenceRow).where(
                models.ResourceReferenceRow.recorded_at < cutoff
            )
        )
        await self.session.flush()
        return rows_affected(transitions) + rows_affected(references)

    async def audit_event_count(self) -> int:
        """Return how many audit events the whole deployment holds.

        Not on the port. The retention test uses it to assert that a sweep of
        everything else left the audit trail exactly as it was, which is a
        stronger check than confirming one event survived.
        """
        total = await self.session.scalar(select(func.count()).select_from(models.AuditEvent))
        return int(total or 0)


__all__ = ["PostgresRetentionSweeper"]
