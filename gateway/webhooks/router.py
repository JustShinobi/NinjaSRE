"""The webhook endpoint: verify, dedupe, shed, normalise, and start or link an investigation.

Follows the plan's flow exactly: payload cap, then verification, then
idempotency, then team routing (verification and routing are the same step
here — see ``WebhookSourceConfig``), then the rate limiter, then
normalisation, then deduplication, and only then a run. Every rejection along
the way is a 4xx with a named reason; nothing is dropped without a trace of
why (FR-020).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, Request, Response

from config.constants.runs import TRIGGER_ALERT
from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES
from core.domain.alerts.normalisation import RawAlert, adapter_for
from gateway.http.errors import ApiProblem
from gateway.http.orchestration import start_investigation
from gateway.http.state import GatewayState
from gateway.webhooks.dedup import fingerprint
from gateway.webhooks.sources import (
    alertmanager,
    datadog,
    generic,
    grafana,
    opsgenie,
    pagerduty,
    sentry,
)
from gateway.webhooks.sources.profile import WebhookSourceProfile
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RunRecorder

logger = get_logger(__name__)

#: The seven configured path segments, each with the normalisation profile
#: that already exists for it (feature 005).
PROFILES: dict[str, WebhookSourceProfile] = {
    "alertmanager": alertmanager.PROFILE,
    "pagerduty": pagerduty.PROFILE,
    "datadog": datadog.PROFILE,
    "grafana": grafana.PROFILE,
    "sentry": sentry.PROFILE,
    "opsgenie": opsgenie.PROFILE,
    "generic": generic.PROFILE,
}


@runtime_checkable
class WebhookVerifier(Protocol):
    """What every verification mechanism implements (FR-015)."""

    def verify(self, *, headers: Mapping[str, str], body: bytes) -> bool:
        """Return whether ``body`` is authentic under this verifier's secret."""


@dataclass(frozen=True, slots=True)
class WebhookSourceConfig:
    """One team's route onto one source's webhook path (FR-023).

    An operator gives every team its own verifier against the same URL, and
    whichever one verifies the request decides the team — routing and
    authentication are the same decision, which is what keeps one endpoint
    from needing a second mechanism to tell its callers apart.
    """

    verifier: WebhookVerifier
    org_id: str
    team_node_id: str
    principal_id: str = "system:webhook"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_webhook_router(
    state: GatewayState,
    *,
    routes: Mapping[str, Sequence[WebhookSourceConfig]] | None = None,
) -> APIRouter:
    """Return the router serving every configured webhook path.

    ``routes`` is empty by default: a deployment with no webhook sources
    configured serves every path with "nothing verifies", which is a 401 and
    an audit line rather than a route that does not exist.
    """
    configured = routes if routes is not None else {}
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    for path_name, profile in PROFILES.items():
        router.add_api_route(
            f"/{path_name}",
            _handler(state, path_name, profile, tuple(configured.get(path_name, ()))),
            methods=["POST"],
        )

    return router


def _handler(
    state: GatewayState,
    path_name: str,
    profile: WebhookSourceProfile,
    source_routes: tuple[WebhookSourceConfig, ...],
) -> Callable[[Request], Awaitable[Response]]:
    async def handle(request: Request) -> Response:
        body = await request.body()
        if len(body) > WEBHOOK_MAX_PAYLOAD_BYTES:
            raise ApiProblem(
                status_code=413,
                error_type="payload_too_large",
                message=f"{path_name} payload of {len(body)} bytes exceeds the "
                f"{WEBHOOK_MAX_PAYLOAD_BYTES}-byte cap",
            )

        matched = next(
            (
                route
                for route in source_routes
                if route.verifier.verify(headers=request.headers, body=body)
            ),
            None,
        )
        if matched is None:
            logger.warning("webhooks.unverified", source=path_name)
            raise ApiProblem(
                status_code=401,
                error_type="unverified",
                message=f"this {path_name} webhook did not verify against any configured route",
            )

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as error:
            raise ApiProblem(
                status_code=400,
                error_type="bad_request",
                message=f"{path_name} payload is not valid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise ApiProblem(
                status_code=400,
                error_type="bad_request",
                message=f"{path_name} payload must be a JSON object",
            )

        event_id = profile.event_id_of(payload)
        if state.webhook_idempotency.already_processed(path_name, event_id):
            return _ack({"acknowledged": True, "duplicate_delivery": True})

        if not state.webhook_shedder.admit(source=path_name, team_node_id=matched.team_node_id):
            return Response(
                status_code=429,
                content=json.dumps({"shed": True, "reason": "rate limit"}),
                media_type="application/json",
            )

        alert = adapter_for(profile.source).normalise(
            RawAlert(payload=payload, received_at=_utc_now())
        )
        key = fingerprint(alert, team_node_id=matched.team_node_id)
        scope = TenantScope(org_id=matched.org_id, team_node_id=matched.team_node_id)
        linked_run = state.webhook_dedup.linked_run(key)

        if alert.resolved:
            state.webhook_idempotency.record(path_name, event_id)
            return await _handle_resolution(
                state, scope=scope, linked_run=linked_run, alert_name=alert.alert_name
            )

        state.webhook_idempotency.record(path_name, event_id)
        if linked_run is not None:
            return _ack({"run_id": linked_run, "linked": True})

        run_id = await start_investigation(
            state,
            scope=scope,
            trigger=TRIGGER_ALERT,
            objective=f"{alert.alert_name}: {alert.summary}".strip(": "),
            principal_id=matched.principal_id,
            alert_source=profile.source.value,
            alert_id=key,
        )
        state.webhook_dedup.link(key, run_id)
        return _ack({"run_id": run_id, "linked": False})

    return handle


async def _handle_resolution(
    state: GatewayState, *, scope: TenantScope, linked_run: str | None, alert_name: str
) -> Response:
    """Link a resolution to its investigation where one exists (FR-019)."""
    if linked_run is None:
        logger.info("webhooks.resolution_without_investigation", alert_name=alert_name)
        return _ack({"resolution": "standalone", "linked": False})

    async with state.gateway.begin(scope) as uow:
        recorder = RunRecorder(
            store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
        )
        await recorder.record_event(
            linked_run,
            TraceEventKind.EVIDENCE_OBSERVED,
            payload={"resolution": True, "alert_name": alert_name},
        )
    return _ack({"resolution": "linked", "run_id": linked_run})


def _ack(body: Mapping[str, object]) -> Response:
    return Response(status_code=202, content=json.dumps(dict(body)), media_type="application/json")


__all__ = ["PROFILES", "WebhookSourceConfig", "WebhookVerifier", "build_webhook_router"]
