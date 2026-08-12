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
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.constants import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from config.constants.deployment import SCHEDULER_TICK_INTERVAL_SECONDS
from config.constants.surfaces import GATEWAY_SHUTDOWN_DRAIN_SECONDS
from gateway.http.change_sources import compose_change_sources
from gateway.http.discovery_sources import compose_discovery_sources, compose_signal_sources
from gateway.http.log_sources import compose_log_sources
from gateway.http.scheduled_work import run_scheduler, worker_for
from gateway.http.state import GatewayState
from platform.observability.logging import get_logger
from platform.startup.bootstrap import organisation_id

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

    # After the store is known to answer, because it is read from the
    # configuration tree — and before the first request, so a resource page
    # never renders "nothing was consulted" for a deployment that had.
    if health.is_ready:
        await compose_change_sources(state, org_id=organisation_id())
        # The same moment and the same reasoning: a deployment whose cluster is
        # configured should have a source before anybody opens the estate,
        # rather than after somebody notices it is empty.
        await compose_discovery_sources(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )
        # The metrics systems, on the same terms. What is composed is a client;
        # the source that uses it is built per tick, because it needs the
        # estate's guests and those change with every sweep.
        await compose_signal_sources(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )
        # The log system, on the same terms. Composed here rather than at the
        # first investigation that wants a line, so a deployment pointed at a
        # Loki has one before anybody asks — and one that is not says so, rather
        # than reporting a resource as quiet.
        await compose_log_sources(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )

    # Nothing else claims a due job, so a deployment that scheduled a sweep and
    # served no scheduler is one whose estate never fills. Started after the
    # sources it dispatches to are composed, and stopped before the store it
    # writes through is closed.
    stop = asyncio.Event()
    scheduler: asyncio.Task[None] | None = None
    if health.is_ready:
        scheduler = asyncio.create_task(
            run_scheduler(
                worker_for(state),
                interval_seconds=SCHEDULER_TICK_INTERVAL_SECONDS,
                stop=stop,
            )
        )

    try:
        yield
    finally:
        stop.set()
        if scheduler is not None:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler
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
