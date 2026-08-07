"""Liveness and readiness: store connectivity, provider availability, migration status (FR-024).

Public — a load balancer checks readiness before it could hold a credential —
and this is the one route family that answers without opening a unit of work,
because a deployment whose store is down still has to be able to say so.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.llm.registry import default_registry
from gateway.http.deps import get_state
from gateway.http.state import GatewayState

router = APIRouter(prefix="/health", tags=["health"])


class LivenessView(BaseModel):
    live: bool


class ReadinessView(BaseModel):
    ready: bool
    store_state: str
    connected: bool
    migrations_current: bool | None = None
    providers_configured: list[str]
    reasons: list[str]
    recent_shedding: list[str]


@router.get("/live", response_model=LivenessView)
async def liveness(state: GatewayState = Depends(get_state)) -> LivenessView:
    """Return whether this process should keep running."""
    health = await state.gateway.health()
    return LivenessView(live=health.is_live)


@router.get("/ready", response_model=ReadinessView)
async def readiness(state: GatewayState = Depends(get_state)) -> ReadinessView:
    """Return whether this deployment should accept work."""
    health = await state.gateway.health()
    recent = state.webhook_shedder.log.all()[-10:]
    return ReadinessView(
        ready=health.is_ready and not state.draining,
        store_state=health.state.value,
        connected=health.connected,
        migrations_current=health.migrations.is_current if health.migrations else None,
        providers_configured=list(default_registry().provider_ids()),
        reasons=list(health.reasons),
        recent_shedding=[record.reason for record in recent],
    )


__all__ = ["router"]
