"""The webhook endpoint: verify, dedupe, shed, normalise, and raise an incident.

The flow is a payload cap, then verification, then idempotency, then team
routing (verification and routing are the same step here — see
``WebhookSourceConfig``), then the rate limiter, then normalisation, then
deduplication, and only then an incident. Every rejection along the way is a
4xx with a named reason; nothing is dropped without a trace of why.

**An ingested alert becomes an incident, not an ``Alert``.** This route used to
start a run directly, and the investigation was the only record that anything
had arrived. It now goes through the same lifecycle a detected condition does,
so a webhook alert and a detector firing produce structurally identical
incidents and nothing downstream has two cases to handle. The run is attached to
the incident rather than standing in for it.

**A resolution closes the incident the firing alert opened.** The upstream's own
fingerprint is the correlation key, so the two find each other without this
deployment holding a second opinion about which alerts are the same alert.

**The alert's labels are resolved against the estate before anything is
raised.** ``instance``, ``vmid`` and a prober's target are the vocabulary of
whatever sent the alert; every stage after this is keyed by a resource
identifier. The resolution decides the incident's subject and the run's opening
context, and a target this estate does not hold becomes a finding stored on the
incident rather than a label nobody can act on. The rule itself lives in
``platform/estate/alert_resolution.py`` — this handler is a caller, because
062's routing rules and the detectors need the same function and tier 1 must not
own what tiers 2 and 3 want.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, Request, Response

from config.constants.estate import MAX_ESTATE_PAGE_SIZE
from config.constants.runs import TRIGGER_ALERT
from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES
from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, adapter_for
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
from platform.estate.alert_resolution import AlertResolution, resolve_alert
from platform.incidents.dispatch import objective_for
from platform.incidents.ingestion import raise_for_alert, resolution_key
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    ReferenceKind,
    ResourceReference,
)
from platform.persistence.ports.incident_store import Incident
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
        scope = TenantScope(org_id=matched.org_id, team_node_id=matched.team_node_id)
        resolution = await _resolve_against_estate(state, scope=scope, alert=alert)
        key = fingerprint(alert, team_node_id=matched.team_node_id, resolution=resolution)
        linked_run = state.webhook_dedup.linked_run(key)

        if alert.resolved:
            state.webhook_idempotency.record(path_name, event_id)
            return await _handle_resolution(
                state,
                scope=scope,
                linked_run=linked_run,
                alert_name=alert.alert_name,
                correlation_key=resolution_key(source=profile.source.value, fingerprint=key),
            )

        state.webhook_idempotency.record(path_name, event_id)
        incident = await _raise_incident(
            state,
            scope=scope,
            alert=alert,
            source=profile.source.value,
            key=key,
            matched=matched,
            resolution=resolution,
        )
        await _link_resource(
            state,
            scope=scope,
            resolution=resolution,
            kind=ReferenceKind.INCIDENT,
            reference_id=incident.incident_id,
            summary=incident.title,
        )

        if linked_run is not None:
            return _ack({"run_id": linked_run, "incident_id": incident.incident_id, "linked": True})

        run_id = await start_investigation(
            state,
            scope=scope,
            trigger=TRIGGER_ALERT,
            objective=objective_for(incident),
            principal_id=matched.principal_id,
            alert_source=profile.source.value,
            alert_id=key,
            context=_investigation_context(resolution),
        )
        state.webhook_dedup.link(key, run_id)
        await _link_resource(
            state,
            scope=scope,
            resolution=resolution,
            kind=ReferenceKind.RUN,
            reference_id=run_id,
            summary=incident.title,
        )
        async with state.gateway.begin(scope) as uow:
            await IncidentLifecycle(store=uow.incidents).attach_run(
                incident.incident_id,
                run_id,
                objective=objective_for(incident),
                now=_utc_now(),
            )
        return _ack({"run_id": run_id, "incident_id": incident.incident_id, "linked": False})

    return handle


async def _resolve_against_estate(
    state: GatewayState,
    *,
    scope: TenantScope,
    alert: NormalisedAlert,
) -> AlertResolution:
    """Return which estate resource ``alert`` is about, or the finding that it is not.

    One bounded read of the estate per delivery. The repository has no attribute
    filter — ``instance``, ``vmid`` and a declared domain are all attributes —
    so the page is what resolution matches against, exactly as enrichment does.
    An estate larger than the page bound resolves against its first page, which
    is the same limit 053 recorded and the same cursor 062 is asked for.
    """
    async with state.gateway.begin(scope) as uow:
        resources = await uow.estate.query(EstateQuery(limit=MAX_ESTATE_PAGE_SIZE))
    resolution = resolve_alert(alert, resources=resources)
    if resolution.unresolved is not None:
        logger.info(
            "webhooks.unresolved_target",
            source=alert.alert_source.value,
            alert_name=alert.alert_name,
            label=resolution.unresolved.label,
            target=resolution.unresolved.value,
            zone=resolution.unresolved.zone,
        )
    return resolution


def _investigation_context(resolution: AlertResolution) -> Mapping[str, str]:
    """Return what the run is told about its subject before its first turn.

    Empty when nothing resolved, deliberately: a context naming a resource this
    deployment does not hold would send the agent looking for it, and "we do not
    know what this is about" is already on the incident where a person reads it.
    """
    target = resolution.resolved
    if target is None:
        return {}
    return {
        "resource_id": target.resource_id,
        "resource_kind": target.kind,
        "resource_name": target.display_name,
        "resource_zone": target.zone,
        "resolved_from": f"{target.label}={target.value}",
    }


async def _link_resource(
    state: GatewayState,
    *,
    scope: TenantScope,
    resolution: AlertResolution,
    kind: ReferenceKind,
    reference_id: str,
    summary: str,
) -> None:
    """Record on the resource that this incident or run touched it.

    Only when the alert resolved. A reference from a target nothing matched
    would have no resource to hang on, which is what the finding on the incident
    is for instead.
    """
    target = resolution.resolved
    if target is None:
        return
    async with state.gateway.begin(scope) as uow:
        await uow.estate.link(
            ResourceReference(
                resource_id=target.resource_id,
                reference_kind=kind,
                reference_id=reference_id,
                recorded_at=_utc_now(),
                summary=summary,
            )
        )


async def _raise_incident(
    state: GatewayState,
    *,
    scope: TenantScope,
    alert: NormalisedAlert,
    source: str,
    key: str,
    matched: WebhookSourceConfig,
    resolution: AlertResolution,
) -> Incident:
    """Raise — or correlate onto — the incident this alert belongs to.

    Through the same lifecycle a detected condition uses. There is no second
    constructor here and no ``Alert`` record: the whole point of the
    unification is that everything downstream sees one kind of thing.
    """
    async with state.gateway.begin(scope) as uow:
        return await IncidentLifecycle(store=uow.incidents).raise_incident(
            raise_for_alert(
                source=source,
                fingerprint=key,
                alert_name=alert.alert_name,
                summary=alert.summary,
                description=alert.description,
                severity=alert.severity.value,
                components=alert.components,
                team_node_id=matched.team_node_id,
                reference=alert.reference,
                actor=matched.principal_id,
                resolution=resolution,
                group_key=alert.group_key,
            ),
            now=_utc_now(),
        )


async def _handle_resolution(
    state: GatewayState,
    *,
    scope: TenantScope,
    linked_run: str | None,
    alert_name: str,
    correlation_key: str,
) -> Response:
    """Close the incident the firing alert opened, and tell its run about it.

    The incident closes whether or not a run was linked. An upstream that has
    gone green and a deployment still showing the incident open is the
    disagreement this closes; recording it only on the run would leave the
    incident list wrong.
    """
    closed: str | None = None
    async with state.gateway.begin(scope) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await uow.incidents.open_for(correlation_key)
        if incident is not None:
            await lifecycle.self_close(
                incident.incident_id,
                cause=f"{alert_name or 'the alert'} was resolved upstream",
                now=_utc_now(),
            )
            closed = incident.incident_id

        if linked_run is not None:
            recorder = RunRecorder(
                store=uow.run_traces, guardrails=state.guardrails, broker=state.broker
            )
            await recorder.record_event(
                linked_run,
                TraceEventKind.EVIDENCE_OBSERVED,
                payload={"resolution": True, "alert_name": alert_name},
            )

    if linked_run is None:
        logger.info("webhooks.resolution_without_investigation", alert_name=alert_name)
        return _ack({"resolution": "standalone", "linked": False, "incident_id": closed})
    return _ack({"resolution": "linked", "run_id": linked_run, "incident_id": closed})


def _ack(body: Mapping[str, object]) -> Response:
    return Response(status_code=202, content=json.dumps(dict(body)), media_type="application/json")


__all__ = ["PROFILES", "WebhookSourceConfig", "WebhookVerifier", "build_webhook_router"]
