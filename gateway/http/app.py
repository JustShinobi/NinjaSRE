"""The FastAPI application: versioned routing, OpenAPI, and every boundary wired once."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import FastAPI

from gateway.http.correlation import CorrelationIdMiddleware
from gateway.http.errors import install_error_handlers
from gateway.http.lifespan import lifespan
from gateway.http.routes import (
    agent,
    approvals,
    audit,
    autonomy,
    capabilities,
    config,
    estate,
    estate_discovery,
    first_run,
    health,
    identity,
    incidents,
    ingress,
    integrations,
    interactions,
    investigations,
    knowledge,
    memory,
    providers,
    remediation,
    runs,
    schedules,
    sso,
    threads,
    topology,
    transit,
)
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig, build_webhook_router

API_TITLE = "NinjaSRE API"
API_VERSION = "v1"

#: FR-005. A version is supported for at least this long after whatever
#: replaces it ships; a deprecated version answers every request with a
#: ``Deprecation`` header naming the date support ends.
API_DEPRECATION_POLICY = (
    "Each API version is supported for at least twelve months after the version that "
    "replaces it ships. A deprecated version's responses carry a 'Deprecation' header "
    "naming the date support ends."
)


def create_app(
    state: GatewayState,
    *,
    webhook_routes: Mapping[str, Sequence[WebhookSourceConfig]] | None = None,
) -> FastAPI:
    """Return the wired application, with ``state`` reachable from every request.

    ``webhook_routes`` is the operator's per-source, per-team verification
    configuration (FR-023) — empty by default, which means every webhook path
    exists but nothing can verify against it, so an unconfigured deployment
    audits and rejects rather than exposing an open ingestion endpoint.
    """
    app = FastAPI(
        title=API_TITLE,
        version="1.0.0",
        description=API_DEPRECATION_POLICY,
        lifespan=lifespan,
    )
    app.state.gateway_state = state

    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)

    for router in (
        agent.router,
        autonomy.router,
        incidents.router,
        investigations.router,
        threads.router,
        interactions.investigations_router,
        interactions.interactions_router,
        runs.router,
        config.router,
        integrations.router,
        ingress.router,
        transit.router,
        memory.router,
        remediation.router,
        schedules.router,
        capabilities.router,
        estate_discovery.router,
        estate.router,
        approvals.router,
        topology.router,
        knowledge.router,
        first_run.router,
        providers.router,
        identity.auth_router,
        identity.identity_router,
        sso.router,
        audit.router,
        health.router,
    ):
        app.include_router(router)

    app.include_router(build_webhook_router(state, routes=webhook_routes))

    return app


__all__ = ["API_DEPRECATION_POLICY", "API_TITLE", "API_VERSION", "create_app"]
