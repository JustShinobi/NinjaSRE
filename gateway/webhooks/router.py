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
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, Protocol, runtime_checkable

from fastapi import APIRouter, Request, Response

from config.constants.estate import MAX_ESTATE_PAGE_SIZE
from config.constants.runs import TRIGGER_ALERT
from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES
from config.constants.transit import (
    RULE_ACTION_DISCARD,
    RULE_ACTION_RECORD_ONLY,
    TRANSIT_SHED_LEDGER_INTERVAL,
)
from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, adapter_for
from gateway.http.errors import ApiProblem
from gateway.http.orchestration import start_investigation
from gateway.http.state import GatewayState
from gateway.webhooks.dedup import fingerprint
from gateway.webhooks.sources import (
    alertmanager,
    generic,
    grafana,
)
from gateway.webhooks.sources.profile import WebhookSourceProfile
from platform.config_service.bindings import masking_policy
from platform.config_service.errors import UnknownNode
from platform.config_service.schema import RootConfig
from platform.config_service.service import ConfigService
from platform.estate.alert_resolution import AlertResolution, resolve_alert
from platform.identity.errors import TokenRejected
from platform.identity.permissions import Permission
from platform.incidents.dispatch import objective_for
from platform.incidents.ingestion import raise_for_alert, resolution_key
from platform.incidents.lifecycle import IncidentLifecycle
from platform.ingress.ledger import delivery_key, masked_sample, record_delivery
from platform.ingress.rules import RuleMatch, Signals, evaluate
from platform.observability.logging import get_logger
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    ReferenceKind,
    ResourceReference,
    whole_estate,
)
from platform.persistence.ports.incident_store import Incident
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.transit_ledger import PayloadSample, TransitOutcome
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RunRecorder

logger = get_logger(__name__)

#: The three configured path segments this deployment answers alerts on, each
#: with the normalisation profile that already exists for it (feature 005).
PROFILES: dict[str, WebhookSourceProfile] = {
    "alertmanager": alertmanager.PROFILE,
    "grafana": grafana.PROFILE,
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
    #: The delivery credential's *display* name — never its value. Empty for
    #: a route configured with a shared secret, which names no credential of
    #: its own; set from the token's own stored name when a delivery token
    #: authenticated the request (see ``_delivery_token_route``). Carried
    #: through to the investigation's receipt so a person reading the
    #: incident later knows which credential let this delivery in.
    credential_name: str = ""


#: The scheme a delivery token is presented under, lower-cased for comparison.
_BEARER: Final = "bearer "


@dataclass(frozen=True, slots=True)
class _AlreadyVerified:
    """The verifier a token-authenticated route carries.

    ``WebhookSourceConfig`` needs one, and the request has already been
    authenticated by something stronger than a shared secret. Returning ``True``
    here would be a verifier that verifies anything, so it returns ``False`` and
    is never consulted: nothing puts this instance in ``source_routes``.
    """

    def verify(self, *, headers: Mapping[str, str], body: bytes) -> bool:  # noqa: ARG002 — WebhookVerifier's shape
        """Return ``False``: this route was authenticated before it was built."""
        return False


_ALREADY_VERIFIED: Final = _AlreadyVerified()


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
        received_at = _utc_now()
        body = await request.body()
        delivery_id = delivery_key(source=path_name, received_at=received_at, body=body)

        if len(body) > WEBHOOK_MAX_PAYLOAD_BYTES:
            message = (
                f"{path_name} payload of {len(body)} bytes exceeds the "
                f"{WEBHOOK_MAX_PAYLOAD_BYTES}-byte cap"
            )
            await _ledger_refusal(
                state,
                source_routes,
                delivery_id=delivery_id,
                source=path_name,
                occurred_at=received_at,
                reason=message,
            )
            raise ApiProblem(status_code=413, error_type="payload_too_large", message=message)

        matched = next(
            (
                route
                for route in source_routes
                if route.verifier.verify(headers=request.headers, body=body)
            ),
            None,
        )
        if matched is None:
            matched = await _delivery_token_route(state, headers=request.headers)
        if matched is None:
            logger.warning("webhooks.unverified", source=path_name)
            message = f"this {path_name} webhook did not verify against any configured route"
            await _ledger_refusal(
                state,
                source_routes,
                delivery_id=delivery_id,
                source=path_name,
                occurred_at=received_at,
                reason=message,
                known_token_refusal=await _known_token_refusal(state, headers=request.headers),
            )
            raise ApiProblem(status_code=401, error_type="unverified", message=message)

        scope = TenantScope(org_id=matched.org_id, team_node_id=matched.team_node_id)
        recorded = _Ledgering(
            state=state,
            scope=scope,
            delivery_id=delivery_id,
            source=path_name,
            occurred_at=received_at,
            team_node_id=matched.team_node_id,
        )

        # The sample and the rule set are both read from configuration, and both
        # are deferred until this delivery is known to be worth acting on. A
        # storm past the shed limit therefore costs an idempotency lookup and a
        # window check, which is the whole point of shedding: the rate limiter
        # must not be the most expensive step on the path it exists to cheapen.
        # A body that would not parse is the exception — that is exactly when
        # somebody needs to see what arrived — so it captures its sample first.
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as error:
            message = f"{path_name} payload is not valid JSON"
            recorded.sample = await _sample_of(
                state, matched, body, path_name, received_at, delivery_id
            )
            await recorded.refused(message)
            raise ApiProblem(status_code=400, error_type="bad_request", message=message) from error
        if not isinstance(payload, dict):
            message = f"{path_name} payload must be a JSON object"
            recorded.sample = await _sample_of(
                state, matched, body, path_name, received_at, delivery_id
            )
            await recorded.refused(message)
            raise ApiProblem(status_code=400, error_type="bad_request", message=message)

        event_id = profile.event_id_of(payload)
        if state.webhook_idempotency.already_processed(path_name, event_id):
            await recorded.duplicate()
            return _ack({"acknowledged": True, "duplicate_delivery": True})

        if not state.webhook_shedder.admit(source=path_name, team_node_id=matched.team_node_id):
            await _ledger_shed(state, scope=scope, source=path_name, team=matched.team_node_id)
            return Response(
                status_code=429,
                content=json.dumps({"shed": True, "reason": "rate limit"}),
                media_type="application/json",
            )

        settings = await _settings(state, matched)
        recorded.sample = masked_sample(
            body,
            source=path_name,
            captured_at=received_at,
            policy=masking_policy(settings.policies),
            delivery_id=delivery_id,
        )

        alert = adapter_for(profile.source).normalise(
            RawAlert(payload=payload, received_at=_utc_now())
        )
        resolution = await _resolve_against_estate(state, scope=scope, alert=alert)

        # Verification decided who this is; the rules decide what happens to it.
        # Evaluated here rather than inside any of the branches below so that
        # every one of them — resolution, discard, record-only, investigate —
        # is reported as the doing of one named rule.
        match = evaluate(
            settings.transit.rule_set(), _signals(path_name, alert, resolution, matched)
        )
        routed = replace(matched, team_node_id=match.team_node_id)
        scope = TenantScope(org_id=routed.org_id, team_node_id=routed.team_node_id)
        recorded = replace(recorded, scope=scope, team_node_id=routed.team_node_id)

        key = fingerprint(alert, team_node_id=routed.team_node_id, resolution=resolution)
        linked_run = state.webhook_dedup.linked_run(key)

        if match.action == RULE_ACTION_DISCARD:
            # Still idempotent and still ledgered. A discard is a decision this
            # deployment took, and the row saying so is the difference between
            # "it never arrived" and "it arrived and we chose not to act".
            state.webhook_idempotency.record(path_name, event_id)
            await recorded.discarded(match)
            return _ack({"discarded": True, "rule": match.rule.rule_id, "reason": match.reason})

        if alert.resolved:
            state.webhook_idempotency.record(path_name, event_id)
            answer = await _handle_resolution(
                state,
                scope=scope,
                linked_run=linked_run,
                alert_name=alert.alert_name,
                correlation_key=resolution_key(source=profile.source.value, fingerprint=key),
            )
            await recorded.accepted(match, resolution=resolution, run_id=linked_run or "")
            return answer

        state.webhook_idempotency.record(path_name, event_id)
        incident = await _raise_incident(
            state,
            scope=scope,
            alert=alert,
            source=profile.source.value,
            key=key,
            matched=routed,
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

        if match.action == RULE_ACTION_RECORD_ONLY:
            # The incident is raised and nothing investigates it. An operator
            # who wanted the record without the spend asked for exactly this,
            # and the row names the rule that granted it.
            await recorded.recorded_only(match, resolution=resolution, incident=incident)
            return _ack(
                {
                    "incident_id": incident.incident_id,
                    "recorded_only": True,
                    "rule": match.rule.rule_id,
                }
            )

        if linked_run is not None:
            await recorded.accepted(
                match, resolution=resolution, run_id=linked_run, incident=incident
            )
            return _ack({"run_id": linked_run, "incident_id": incident.incident_id, "linked": True})

        run_id = await start_investigation(
            state,
            scope=scope,
            trigger=TRIGGER_ALERT,
            objective=objective_for(incident),
            principal_id=routed.principal_id,
            alert_source=profile.source.value,
            alert_id=key,
            context=_investigation_context(resolution),
            incident_id=incident.incident_id,
            alert_labels=alert.labels,
            credential_name=routed.credential_name,
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
        await recorded.accepted(match, resolution=resolution, run_id=run_id, incident=incident)
        return _ack({"run_id": run_id, "incident_id": incident.incident_id, "linked": False})

    return handle


def _signals(
    path_name: str,
    alert: NormalisedAlert,
    resolution: AlertResolution,
    matched: WebhookSourceConfig,
) -> Signals:
    """Return the dimensions a rule may speak about, for this delivery.

    Zone comes from whichever half of the resolution exists: a resolved
    resource carries the estate's own zone, and an unresolved finding carries
    the zone its address sits in. Both are the estate's answer rather than text
    somebody typed, which is what the plan asks a matcher to be.
    """
    resolved = resolution.resolved
    zone = resolved.zone if resolved is not None else ""
    if not zone and resolution.unresolved is not None:
        zone = resolution.unresolved.zone
    return Signals(
        source=path_name,
        zone=zone,
        criticality=alert.severity.value,
        resource_id=resolved.resource_id if resolved is not None else "",
        team_node_id=matched.team_node_id,
    )


@dataclass(slots=True)
class _Ledgering:
    """One delivery's ledger row, written once, whichever way the path went.

    A small object rather than a dozen keyword arguments repeated at nine call
    sites: the identity of the crossing is fixed the moment the request
    arrives, and only the outcome varies. Each method opens its own unit of
    work, deliberately — a rejection has to survive the transaction that
    rejected it, and a row that rolled back with the thing it was recording
    would leave exactly the silence this feature exists to end.

    The masked sample rides along rather than being written when it is taken.
    The row and the payload it describes are one fact, so they commit together
    — and on the ingress path that also means one transaction per delivery
    instead of two, which matters because this is the path a storm arrives on.
    """

    state: GatewayState
    scope: TenantScope
    delivery_id: str
    source: str
    occurred_at: datetime
    team_node_id: str
    sample: PayloadSample | None = None

    async def refused(self, reason: str) -> None:
        """Record a delivery this deployment would not parse."""
        await self._write(TransitOutcome.REJECTED, reason=reason)

    async def duplicate(self) -> None:
        """Record a delivery this deployment had already processed."""
        await self._write(TransitOutcome.DUPLICATE, reason="already processed")

    async def discarded(self, match: RuleMatch) -> None:
        """Record a delivery a rule discarded, and why."""
        await self._write(
            TransitOutcome.DISCARDED, reason=match.reason, matched_rule=match.rule.rule_id
        )

    async def recorded_only(
        self, match: RuleMatch, *, resolution: AlertResolution, incident: Incident
    ) -> None:
        """Record a delivery a rule kept without investigating."""
        await self._write(
            TransitOutcome.RECORDED,
            matched_rule=match.rule.rule_id,
            resolution=resolution,
            incident_id=incident.incident_id,
        )

    async def accepted(
        self,
        match: RuleMatch,
        *,
        resolution: AlertResolution,
        run_id: str = "",
        incident: Incident | None = None,
    ) -> None:
        """Record a delivery this deployment acted on."""
        await self._write(
            TransitOutcome.ACCEPTED,
            matched_rule=match.rule.rule_id,
            resolution=resolution,
            run_id=run_id,
            incident_id="" if incident is None else incident.incident_id,
        )

    async def _write(
        self,
        outcome: TransitOutcome,
        *,
        reason: str = "",
        matched_rule: str = "",
        resolution: AlertResolution | None = None,
        run_id: str = "",
        incident_id: str = "",
    ) -> None:
        resolved = None if resolution is None else resolution.resolved
        detail: dict[str, str] = {}
        if resolution is not None and resolution.unresolved is not None:
            detail["unresolved_target"] = resolution.unresolved.value
        async with self.state.gateway.begin(self.scope) as uow:
            if self.sample is not None:
                await uow.transit.store_sample(self.sample)
            await record_delivery(
                uow,
                delivery_id=self.delivery_id,
                source=self.source,
                occurred_at=self.occurred_at,
                outcome=outcome,
                reason=reason,
                matched_rule=matched_rule,
                team_node_id=self.team_node_id,
                resource_id="" if resolved is None else resolved.resource_id,
                run_id=run_id,
                incident_id=incident_id,
                detail=detail,
            )


async def _sample_of(
    state: GatewayState,
    matched: WebhookSourceConfig,
    body: bytes,
    source: str,
    at: datetime,
    delivery_id: str,
) -> PayloadSample:
    """Return the masked sample of a body this deployment could not parse.

    The one place a sample is taken off the ordinary path, because "the format
    changed" is precisely the question a parse failure raises, and answering it
    from the screen is why the sample exists at all.
    """
    settings = await _settings(state, matched)
    return masked_sample(
        body,
        source=source,
        captured_at=at,
        policy=masking_policy(settings.policies),
        delivery_id=delivery_id,
    )


async def _ledger_shed(
    state: GatewayState,
    *,
    scope: TenantScope,
    source: str,
    team: str,
) -> None:
    """Record that a storm is being shed, as one row per storm rather than per request.

    A shed row is keyed on the source, the team and the window it happened in,
    so a thousand refusals inside one window upsert onto one row carrying how
    many there were. That is the honest shape: a storm is one fact, and a row
    per refused request would be the unbounded growth the shedder exists to
    prevent, paid in the store instead of in the investigator.

    Rewritten every ``TRANSIT_SHED_LEDGER_INTERVAL`` sheds rather than on every
    one, because a load shedder that spends a write per shed is doing the work
    it is refusing to do. The count on the row therefore trails a running storm
    by up to that many deliveries, and is exact once the storm stops.
    """
    shedder = state.webhook_shedder
    shed = shedder.log.most_recent(source=source, team_node_id=team)
    if shed is None:  # pragma: no cover — admit() logs before returning False
        return
    dropped = shed.count_in_window - shedder.max_requests
    if dropped != 1 and dropped % TRANSIT_SHED_LEDGER_INTERVAL != 0:
        return
    # The instant floored to the shedder's own window length, so every refusal
    # inside one storm derives the same key and upserts onto one row.
    window = int(shed.occurred_at.timestamp() // shedder.window_seconds)
    async with state.gateway.begin(scope) as uow:
        await record_delivery(
            uow,
            delivery_id=f"{source}:shed:{team}:{window}",
            source=source,
            occurred_at=shed.occurred_at,
            outcome=TransitOutcome.SHED,
            reason=shed.reason,
            team_node_id=team,
            detail={"shed_in_window": str(dropped)},
        )


async def _ledger_refusal(
    state: GatewayState,
    source_routes: tuple[WebhookSourceConfig, ...],
    *,
    delivery_id: str,
    source: str,
    occurred_at: datetime,
    reason: str,
    known_token_refusal: tuple[TenantScope, str] | None = None,
) -> None:
    """Record a refusal that happened before anything established a tenant.

    ``known_token_refusal`` takes priority when the caller has one. A
    delivery token this deployment issued and later revoked or let expire
    still names its own tenant — resolved by ``_known_token_refusal`` below —
    independent of whatever ``WebhookSourceConfig`` this path happens to have
    configured. That matters because a real deployment configures none: both
    serving entry points call ``create_app`` with no ``webhook_routes`` at
    all, and the delivery token is the trust mechanism this feature asks an
    operator to use. Without this, a revoked token's next delivery would fall
    through to the fallback below, find no configured route either, and write
    nothing — the exact silence the revoked-token edge case exists to avoid.

    Otherwise, against the organisation of the *first* route configured for
    this path. A refusal is a fact about the endpoint, and the endpoint's
    owner is whoever configured it; writing one row per tenant instead would
    multiply an unauthenticated request's storage cost by the number of
    tenants, which is a denial-of-service surface rather than a feature.

    A path with neither a resolved token nor a configured route has no tenant
    to attribute anything to, and the warning in the log is the whole of the
    record — which is honest: nothing here was ever asked for, and that is
    the same "nothing has arrived" a blocked network route produces.
    """
    if known_token_refusal is not None:
        scope, token_reason = known_token_refusal
        await _Ledgering(
            state=state,
            scope=scope,
            delivery_id=delivery_id,
            source=source,
            occurred_at=occurred_at,
            team_node_id=scope.team_node_id or "",
        ).refused(token_reason)
        return
    if not source_routes:
        return
    owner = source_routes[0]
    await _Ledgering(
        state=state,
        scope=TenantScope(org_id=owner.org_id, team_node_id=owner.team_node_id),
        delivery_id=delivery_id,
        source=source,
        occurred_at=occurred_at,
        team_node_id="",
    ).refused(reason)


async def _known_token_refusal(
    state: GatewayState, *, headers: Mapping[str, str]
) -> tuple[TenantScope, str] | None:
    """Return the tenant and cause for a delivery this deployment once issued
    a credential for, but which just failed to authenticate — or ``None``
    when the presented value was never a token this deployment issued.

    ``TokenService.authenticate`` (used by ``_delivery_token_route`` above)
    deliberately forgets whether a rejected token was unknown, revoked, or
    expired before that answer ever reaches an audit trail — right on the
    authentication path, so a guess against this endpoint learns nothing from
    the difference. ``TokenDirectory.find_token_by_hash`` is the one place
    that answer is allowed to exist, and its own docstring names exactly one
    legitimate caller: writing the audit row for a rejection already decided
    on. This is that caller. Without it, a delivery token an operator
    configured and later revoked reads on Alert intake as silence
    indistinguishable from a route nobody ever pointed here — precisely the
    outcome the revoked-token edge case exists to prevent.

    A missing, garbage, or never-issued value returns ``None`` and stays
    silent. That silence is correct, not a gap: nothing this deployment ever
    trusted attempted the delivery, which is the same "nothing has arrived" a
    blocked network route produces, and there is no tenant to charge it to.
    """
    presented = headers.get("authorization", "")
    if not presented.lower().startswith(_BEARER):
        return None
    secret = presented[len(_BEARER) :].strip()
    if not secret:
        return None

    token_hash = state.tokens.hasher.hash(secret)
    async with state.gateway.begin_system() as system:
        location = await system.tokens.find_token_by_hash(token_hash)
    if location is None:
        return None

    token = location.token
    if token.is_revoked:
        reason = f"the delivery token {token.name!r} has been revoked"
    elif token.expires_at is not None and token.expires_at <= _utc_now():
        reason = f"the delivery token {token.name!r} has expired"
    elif Permission.WEBHOOK_DELIVER.value not in token.scopes:
        reason = f"the delivery token {token.name!r} is not scoped to deliver alerts"
    else:
        reason = f"the delivery token {token.name!r} did not verify"

    scope = TenantScope(org_id=location.org_id, team_node_id=token.team_node_id or "")
    return scope, reason


async def _settings(state: GatewayState, matched: WebhookSourceConfig) -> RootConfig:
    """Return the routed team's effective configuration.

    Resolved per delivery rather than held on the state, which is the pattern
    every other route here follows: a rule an operator added thirty seconds ago
    decides the next delivery, and a cached rule set would make "when does this
    take effect" a question about process lifetime.
    """
    scope = TenantScope(org_id=matched.org_id, team_node_id=matched.team_node_id)
    service = ConfigService(gateway=state.gateway, scope=scope, guardrails=state.guardrails)
    # The team first, then the organisation root. A verifier may name a team the
    # tree has no node for — routing is configured beside the receiver, and the
    # hierarchy is configured somewhere else — and falling back to the root is
    # what inheritance would have given had the node existed. Falling back to
    # the shipped defaults instead would silently ignore the rules an operator
    # wrote one level up, which is the failure this feature is about.
    for node_id in (matched.team_node_id, matched.org_id):
        if not node_id:
            continue
        try:
            return (await service.resolve(node_id)).config
        except (UnknownNode, RecordNotFound):
            continue
    # A deployment with no configuration tree at all still ingests. Refusing an
    # alert because nobody has configured anything would make configuration a
    # precondition for the platform working.
    return RootConfig()


async def _delivery_token_route(
    state: GatewayState,
    *,
    headers: Mapping[str, str],
) -> WebhookSourceConfig | None:
    """Return the route a delivery token presents, or ``None``.

    Tried only after every configured verifier declined, which keeps it purely
    additive: a source an operator wired with a signature or a shared secret
    verifies exactly as it did, including the ones whose shared secret rides in
    the same ``Authorization`` header this reads.

    The token decides the team, which keeps routing and authentication one
    decision — the same property ``WebhookSourceConfig`` holds, reached the
    other way. ``WEBHOOK_DELIVER`` and nothing else is required, and it is the
    narrowest permission there is on purpose: this credential lives in an alert
    router's configuration file, outside anything this deployment rotates.
    """
    presented = headers.get("authorization", "")
    if not presented.lower().startswith(_BEARER):
        return None
    secret = presented[len(_BEARER) :].strip()
    if not secret:
        return None

    try:
        token = await state.tokens.authenticate(secret)
    except TokenRejected:
        return None
    # Checked at the node the token was issued for, which is the node its team
    # routing comes from. Asking at the root would refuse a token granted
    # exactly where it is meant to deliver.
    if not token.permissions.allows(Permission.WEBHOOK_DELIVER, node_id=token.scope.team_node_id):
        logger.warning(
            "webhooks.token_without_delivery_permission", principal=token.principal.principal_id
        )
        return None

    return WebhookSourceConfig(
        verifier=_ALREADY_VERIFIED,
        org_id=token.scope.org_id,
        team_node_id=token.scope.team_node_id or "",
        principal_id=token.principal.principal_id,
        credential_name=token.token.name,
    )


async def _resolve_against_estate(
    state: GatewayState,
    *,
    scope: TenantScope,
    alert: NormalisedAlert,
) -> AlertResolution:
    """Return which estate resource ``alert`` is about, or the finding that it is not.

    The whole estate per delivery, paged. The repository has no attribute
    filter — ``instance``, ``vmid`` and a declared domain are all attributes —
    so what resolution matches against is the resources themselves. This read
    used to be one page, and an estate larger than it produced an unresolved
    finding for a guest that was there: a *false* finding, which is worse than
    a slow one. Paging is one query for any estate that fits in a page, which
    is every deployment this has run against so far.
    """
    async with state.gateway.begin(scope) as uow:
        resources = await whole_estate(uow.estate, EstateQuery(limit=MAX_ESTATE_PAGE_SIZE))
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
