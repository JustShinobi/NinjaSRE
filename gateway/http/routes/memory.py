"""Memory: search episodes by component, and corpus stats.

Reads ``EpisodeStore`` directly rather than through the full ``MemoryService``,
which also needs an embedder and an LLM for similarity search and synthesis —
composing a runtime is a deployment concern (feature 030), same as starting an
investigation. What this route serves is the exact-match half of recall:
component and recency, which needs no model attached.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.persistence.ports.episode_store import Episode

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class EpisodeView(BaseModel):
    episode_id: str
    title: str
    summary: str
    outcome: str
    components: list[str]
    occurred_at: str | None = None


class SearchResult(BaseModel):
    episodes: list[EpisodeView]


class MemoryStats(BaseModel):
    episode_count: int


def _view(episode: Episode) -> EpisodeView:
    return EpisodeView(
        episode_id=episode.episode_id,
        title=episode.title,
        summary=episode.summary,
        outcome=episode.outcome.value,
        components=list(episode.components),
        occurred_at=episode.occurred_at.isoformat() if episode.occurred_at else None,
    )


@router.get("/search", response_model=SearchResult)
async def search_memory(
    component: str = "",
    limit: int = 20,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> SearchResult:
    """Return episodes involving ``component``, most recent first."""
    async with state.gateway.begin(auth.scope) as uow:
        if component:
            episodes = await uow.episodes.by_component(component, limit=limit)
        else:
            episodes = await uow.episodes.list_recent(limit=limit)
    return SearchResult(episodes=[_view(episode) for episode in episodes])


@router.get("/stats", response_model=MemoryStats)
async def memory_stats(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> MemoryStats:
    """Return what the episodic corpus holds for this team."""
    async with state.gateway.begin(auth.scope) as uow:
        count = await uow.episodes.count()
    return MemoryStats(episode_count=count)


__all__ = ["router"]
