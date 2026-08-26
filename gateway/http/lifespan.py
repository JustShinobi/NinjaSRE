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
from config.constants.executor import NINJASRE_NODE_EXECUTOR_URL_ENV
from config.constants.surfaces import GATEWAY_SHUTDOWN_DRAIN_SECONDS
from gateway.http.change_sources import compose_change_sources
from gateway.http.control_plane import compose_control_plane
from gateway.http.deep_verification import compose_deep_verifier
from gateway.http.discovery_sources import compose_discovery_sources, compose_signal_sources
from gateway.http.enrichment_plans import compose_enrichment_plans_for
from gateway.http.integration_access import compose_integration_access
from gateway.http.log_sources import compose_log_sources
from gateway.http.memory_sources import compose_memory
from gateway.http.node_access import compose_node_access
from gateway.http.provider_credentials import compose_provider_credentials
from gateway.http.remediation import compose_remediation
from gateway.http.runtime import recompose_investigator
from gateway.http.scheduled_work import run_scheduler, worker_for
from gateway.http.state import GatewayState
from gateway.http.topology_sources import compose_topology_sources
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope
from platform.runs.reaping import RunReaper
from platform.runs.recorder import RunRecorder
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
        # Before anything else reads the run store, because until this runs the
        # store answers "running" for runs whose process was killed — a pod
        # evicted mid-deploy, a node lost — and every screen and every count
        # built on that answer is wrong. The graceful path on the way down
        # (``drain``) covers the shutdowns that get a grace period; this covers
        # the ones that do not, which is most of them.
        await _reap_abandoned_runs(state)
        # First, because every vendor tool in the catalogue reads this one
        # binding to make a call, and without it each reports itself
        # unavailable by name — which is a hundred and ninety-three
        # capabilities a deployment has and cannot use.
        await compose_integration_access(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )
        # The provider keys the operator stored, so an investigation calls its
        # model with the credential the console verified rather than with
        # whatever the process environment holds — which, in a deployment
        # configured through the console, is nothing.
        await compose_provider_credentials(state, org_id=organisation_id())
        # And now the runner, again. It was built by `build_deployment` from the
        # environment alone — the only thing a synchronous composition root
        # has — before the model binding was published and before the line
        # above put the vault's keys where the factory reads them. The client
        # it resolved then is cached, so without this the operator's choice is
        # published, correct, and never used.
        recompose_investigator(state)
        # Straight after the binding it reads, because "Test again" is the one
        # control that turns "nobody has checked this" into a measurement, and
        # without this line the route behind it refuses on every deployment.
        compose_deep_verifier(state)
        # The half of the product that acts. Composed here and not earlier for
        # three reasons in order: the executor reaches a control plane through
        # the proxy the first line above binds, it calls a model through the
        # keys the second publishes, and it is handed to the runner — which the
        # line above has just replaced, so composing before it would install the
        # desk on the object that was thrown away and leave the loop that
        # actually runs with none.
        # Before the desk, and that order is the whole of it. The desk asks
        # whether a control plane exists and composes nothing when one does
        # not, so binding afterwards would leave every deployment proposing
        # nothing for a reason no policy chose. Binding authorises nothing: the
        # gate still resolves this deployment's posture when a write is
        # decided, the approval is stored pending, and running it is a second
        # entry through a route a person presses.
        await compose_control_plane(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )
        await compose_remediation(
            state,
            org_id=organisation_id(),
            proxy_url=os.environ.get(NINJASRE_CREDENTIAL_PROXY_URL_ENV, ""),
        )
        # What this deployment remembers, composed per investigation from the
        # run's own team. Here rather than earlier because it attaches to the
        # runner the recomposition above has just replaced, and it resolves the
        # model the operator bound for extraction. Both halves at once: an
        # unbound recall reports honestly that memory is not configured, and a
        # recall bound over a corpus nothing writes to reports that this team
        # has no history — which is the same sentence with the doubt removed.
        compose_memory(state, org_id=organisation_id())
        # The graph a topology question traverses. After the rebuild for the
        # same reason the desk is: this is attached to the runner, and attaching
        # before it would install the factory on the object that was thrown
        # away. What is attached *is* a factory rather than a source, because a
        # graph is read under a tenant scope and one composed here would be one
        # organisation's scope answering every organisation's runs — so the
        # runner builds each investigation its own and binds it for that run.
        # Until this line every investigation that reached for the topology
        # capability was told the graph is not configured, on a deployment whose
        # sweeps had been writing one all along.
        compose_topology_sources(state, org_id=organisation_id())
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
        # What the operator declared about the estate. Read before the
        # scheduler starts, so the first sweep annotates rather than the
        # second.
        await compose_enrichment_plans_for(state, org_id=organisation_id())
        # The node executor, if this deployment runs one. It holds an SSH
        # identity the agent may not hold, so from here it is a vendor like
        # any other: named by address, reached over HTTP, never trusted with
        # a command this side composed.
        await compose_node_access(
            state, executor_url=os.environ.get(NINJASRE_NODE_EXECUTOR_URL_ENV, "")
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
    #
    # Started unconditionally. It used to be gated on the readiness read taken
    # during startup, and that reading is one instant: a store still connecting
    # then is ready a second later, and the gate never asked again — so a
    # deployment that came up a moment early ran no recurring job for the life
    # of the process. That is what it did here: eleven estate sweeps inside one
    # window, then two days of jobs registered, enabled, overdue and unclaimed,
    # with the readiness endpoint answering yes throughout.
    #
    # No readiness parameter replaces the gate, because the loop already
    # degrades correctly without one: a tick against a store that is not there
    # fails, is logged, and is retried on the next interval. A gate would be a
    # second mechanism for what one already handles — and the one that already
    # handles it is the one that can change its mind.
    stop = asyncio.Event()
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
        scheduler.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler
        await drain(state)
        await state.gateway.close()


async def _reap_abandoned_runs(state: GatewayState) -> None:
    """Close the runs no process can still be inside, and never fail the boot.

    Bounded by the wall clock rather than by "this replica is starting", so a
    deployment with more than one replica cannot close a run another replica is
    driving right now. See ``platform.runs.reaping``.
    """
    try:
        scope = TenantScope(org_id=organisation_id())
        async with state.gateway.begin(scope) as uow:
            reaper = RunReaper(
                recorder=RunRecorder(store=uow.run_traces, guardrails=state.guardrails),
                store=uow.run_traces,
            )
            closed = await reaper.reap()
    except Exception as error:  # noqa: BLE001 — tidying must never stop a boot
        logger.warning("gateway.reap_failed", error=str(error))
        return
    logger.info("gateway.runs_reaped", count=len(closed))


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
