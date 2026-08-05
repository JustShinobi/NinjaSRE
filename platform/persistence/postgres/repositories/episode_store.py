"""Episodic memory over PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from platform.persistence.ports.episode_store import Episode, EpisodeOutcome
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    check_limit,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _to_episode(row: models.Episode) -> Episode:
    return Episode(
        episode_id=row.episode_id,
        title=row.title,
        summary=row.summary,
        signature=row.signature,
        outcome=EpisodeOutcome(row.outcome),
        run_id=row.run_id,
        occurred_at=as_utc(row.occurred_at),
        components=as_tuple(row.components),
        tags=as_tuple(row.tags),
        resolution=row.resolution,
        metadata=dict(row.episode_metadata),
    )


@dataclass(slots=True)
class PostgresEpisodeStore(TenantBound):
    """Episodes for one organisation."""

    async def save(self, episode: Episode) -> Episode:
        """Store ``episode``, replacing any earlier version, and return it."""
        row = await self.session.get(models.Episode, (self.org_id, episode.episode_id))
        if row is None:
            row = models.Episode(org_id=self.org_id, episode_id=episode.episode_id)
            self.session.add(row)

        row.title = episode.title
        row.summary = episode.summary
        row.signature = episode.signature
        row.outcome = episode.outcome.value
        row.run_id = episode.run_id
        row.occurred_at = episode.occurred_at
        row.components = as_list(episode.components)
        row.tags = as_list(episode.tags)
        row.resolution = episode.resolution
        row.episode_metadata = check_payload(episode.metadata, kind="episode metadata")

        await self.session.flush()
        return _to_episode(row)

    async def get(self, episode_id: str) -> Episode | None:
        """Return the episode with ``episode_id``, or ``None``."""
        row = await self.session.get(models.Episode, (self.org_id, episode_id))
        return _to_episode(row) if row is not None else None

    async def get_by_run(self, run_id: str) -> Episode | None:
        """Return the episode written for ``run_id``, or ``None``."""
        row = await self.session.scalar(
            select(models.Episode).where(
                models.Episode.org_id == self.org_id, models.Episode.run_id == run_id
            )
        )
        return _to_episode(row) if row is not None else None

    async def by_signature(self, signature: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes sharing a fingerprint, most recent first."""
        check_limit(limit)
        return await self._recent(
            models.Episode.signature == signature,
            limit=limit,
        )

    async def by_component(self, component: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes involving ``component``, most recent first.

        Array containment, so the GIN index on ``components`` answers it. The
        obvious ``ANY(components) = :component`` would not use that index and
        would scan the corpus SC-002 sizes at a hundred thousand rows.
        """
        check_limit(limit)
        return await self._recent(models.Episode.components.contains([component]), limit=limit)

    async def list_recent(
        self,
        *,
        outcome: EpisodeOutcome | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> tuple[Episode, ...]:
        """Return matching episodes, most recent first."""
        check_limit(limit)
        statement = (
            select(models.Episode)
            .where(models.Episode.org_id == self.org_id)
            .order_by(models.Episode.occurred_at.desc(), models.Episode.episode_id.desc())
            .limit(limit)
        )
        if outcome is not None:
            statement = statement.where(models.Episode.outcome == outcome.value)
        if since is not None:
            statement = statement.where(models.Episode.occurred_at >= since)
        if until is not None:
            statement = statement.where(models.Episode.occurred_at < until)
        if since is not None or until is not None:
            statement = statement.where(models.Episode.occurred_at.is_not(None))

        rows = await self.session.scalars(statement)
        return tuple(_to_episode(row) for row in rows)

    async def count(self) -> int:
        """Return how many episodes this tenant holds."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(models.Episode)
            .where(models.Episode.org_id == self.org_id)
        )
        return int(total or 0)

    async def delete(self, episode_id: str) -> bool:
        """Delete ``episode_id`` and return whether it existed."""
        row = await self.session.get(models.Episode, (self.org_id, episode_id))
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def _recent(self, clause: ColumnElement[bool], *, limit: int) -> tuple[Episode, ...]:
        rows = await self.session.scalars(
            select(models.Episode)
            .where(models.Episode.org_id == self.org_id)
            .where(clause)
            .order_by(models.Episode.occurred_at.desc(), models.Episode.episode_id.desc())
            .limit(limit)
        )
        return tuple(_to_episode(row) for row in rows)


__all__ = ["PostgresEpisodeStore"]
