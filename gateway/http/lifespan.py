"""Startup checks and graceful shutdown drain (FR-024, FR-025, SC-008).

Draining stops two different things from happening. A request that arrives
after ``draining`` is set is refused with a reason instead of accepted and then
abandoned mid-run (the edge case the spec names). An investigation already
running when shutdown begins is given a grace period to reach a safe point on
its own; past that, it is asked to stop there directly rather than being torn
down by the process exiting under it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.constants.surfaces import GATEWAY_SHUTDOWN_DRAIN_SECONDS
from gateway.http.state import GatewayState
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Check the store at startup, then drain in-flight runs at shutdown."""
    state: GatewayState = app.state.gateway_state
    health = await state.gateway.health()
    logger.info(
        "gateway.startup",
        store_state=health.state.value,
        connected=health.connected,
        ready=health.is_ready,
        reasons=list(health.reasons),
    )

    try:
        yield
    finally:
        await drain(state)
        await state.gateway.close()


async def drain(
    state: GatewayState, *, timeout_seconds: float = GATEWAY_SHUTDOWN_DRAIN_SECONDS
) -> None:
    """Stop accepting new investigations and give running ones a grace period.

    Runs still going after the grace period are asked to stop at their next
    safe point — never killed — which is what leaves them resumable rather
    than merely interrupted.
    """
    state.draining = True
    in_flight = tuple(state.background_runs)
    if not in_flight:
        logger.info("gateway.shutdown_drained", in_flight=0)
        return

    logger.info("gateway.shutdown_draining", in_flight=len(in_flight))
    _, pending = await asyncio.wait(in_flight, timeout=timeout_seconds)

    if pending:
        logger.warning("gateway.shutdown_grace_period_exceeded", still_running=len(pending))
        for task in pending:
            run_id = task.get_name()
            try:
                await state.investigator.cancel(run_id)
            except Exception as error:  # noqa: BLE001 — every run must be asked, one failure must not stop the rest
                logger.warning("gateway.shutdown_cancel_failed", run_id=run_id, error=str(error))
        await asyncio.wait(pending, timeout=timeout_seconds)

    logger.info("gateway.shutdown_drained", in_flight=len(in_flight))


__all__ = ["drain", "lifespan"]
