"""Where data came from, and where it went — the reads and the one write.

The HTTP half of 062. Four things a screen asks, and they are four questions an
operator asks when something did not arrive:

**Is this source alive?** ``GET /v1/transit/ingress`` answers per source, for
every source this deployment serves rather than for the ones that have
delivered — because a configured source that never delivered is the failure this
whole feature exists to make visible, and a listing built from the ledger alone
could not contain it. ``never_delivered`` is therefore a computed absence, not a
stored flag.

**What did it send, and was it refused?** The masked sample and the recent
rejections, both on the same row.

**What would this rule do?** ``POST /v1/transit/simulate`` runs the *same*
evaluation function the live ingress path runs, over a pasted payload or a
delivery the operator can already see. One implementation called twice, because
a preview computed by a second copy of the logic is a preview that can lie.

**Why has this report not arrived?** The outbound half of the ledger, and
``POST /v1/transit/deliveries/{delivery_id}/resend`` — a human act, audited.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from config.constants.transit import (
    DEFAULT_TRANSIT_PAGE_SIZE,
    DELIVERY_EVENTS,
    NO_DELIVERY_CHANNEL_REASON,
    TRANSIT_ACTIVITY_WINDOW_HOURS,
    TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS,
)
from core.domain.alerts.normalisation import RawAlert, adapter_for
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import bad_request, not_found
from gateway.http.state import GatewayState
from gateway.webhooks.router import PROFILES
from platform.config_service.schema import RootConfig
from platform.config_service.service import ConfigService
from platform.delivery.destinations import declared_destinations, delivery_channels
from platform.delivery.dispatch import DeliveryDispatcher, resend
from platform.estate.alert_resolution import resolve_alert
from platform.ingress.rules import Signals, evaluate
from platform.persistence.ports.estate_repository import EstateQuery
from platform.persistence.ports.transit_ledger import (
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
)

router = APIRouter(prefix="/v1/transit", tags=["transit"])


class DeliveryView(BaseModel):
    """One crossing of the boundary, as a screen renders it."""

    delivery_id: str
    direction: str
    source: str
    occurred_at: str
    outcome: str
    reason: str = ""
    matched_rule: str = ""
    team_node_id: str = ""
    resource_id: str = ""
    run_id: str = ""
    incident_id: str = ""
    event_type: str = ""
    attempt: int = 1
    detail: dict[str, str] = Field(default_factory=dict)


class SampleView(BaseModel):
    """The last payload a source sent, after masking, and which policy did it."""

    captured_at: str
    body: str
    masking_policy: str
    truncated: bool = False


class IngressSourceStatusView(BaseModel):
    """One receiver: where to point it, and whether anything ever arrived."""

    source: str
    path: str
    url: str
    expects: str
    verification: str
    #: The loudest state on the screen. A configured source that never delivered
    #: is indistinguishable from one nobody configured unless this is said.
    never_delivered: bool = True
    last_delivery_at: str = ""
    last_outcome: str = ""
    #: Counts inside the activity window, keyed by outcome.
    counts: dict[str, int] = Field(default_factory=dict)
    #: How many deliveries of any outcome landed inside the last
    #: ``TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS``. A wider, coarser number than
    #: ``counts`` on purpose: "is this still arriving" and "how much has been
    #: arriving" are different questions, asked over different spans.
    week_count: int = 0
    recent_rejections: list[DeliveryView] = Field(default_factory=list)
    sample: SampleView | None = None


class IngressStatusView(BaseModel):
    sources: list[IngressSourceStatusView] = Field(default_factory=list)
    window_hours: int = TRANSIT_ACTIVITY_WINDOW_HOURS


class RuleView(BaseModel):
    """One ordered rule, as the editor renders it."""

    rule_id: str
    sources: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    criticalities: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    team: str = ""
    action: str = ""
    reason: str = ""
    #: Whether this is the rule that decides everything nothing else matched.
    #: Always true of exactly one rule, and it is always the last.
    is_catch_all: bool = False


class RulesView(BaseModel):
    rules: list[RuleView] = Field(default_factory=list)


class SimulationView(BaseModel):
    """What today's rules would do with this payload, before anything is saved."""

    rule_id: str
    action: str
    team: str
    reason: str = ""
    #: What the matchers actually saw, so an operator can tell "no rule matched
    #: this" from "the rule matched something other than what I meant".
    signals: dict[str, str] = Field(default_factory=dict)


class DestinationView(BaseModel):
    """One place results go, and the policy that decides how much of them."""

    destination_id: str
    channel: str
    events: list[str] = Field(default_factory=list)
    detail: str = ""
    enabled: bool = True
    masking_policy: str = ""
    #: Empty when this destination can be delivered to. Filled with the reason
    #: when it cannot — an unconfigurable destination says why rather than
    #: rendering as a working one that silently never sends.
    unconfigurable_reason: str = ""


class DestinationsView(BaseModel):
    destinations: list[DestinationView] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    #: Empty when at least one catalogue integration can deliver a message.
    #: The 054 known-gap posture: a deployment with none says so once, here,
    #: rather than letting every row fail on its own.
    unconfigurable_reason: str = ""


def _view(delivery: TransitDelivery) -> DeliveryView:
    return DeliveryView(
        delivery_id=delivery.delivery_id,
        direction=delivery.direction.value,
        source=delivery.source,
        occurred_at=delivery.occurred_at.isoformat(),
        outcome=delivery.outcome.value,
        reason=delivery.reason,
        matched_rule=delivery.matched_rule,
        team_node_id=delivery.team_node_id,
        resource_id=delivery.resource_id,
        run_id=delivery.run_id,
        incident_id=delivery.incident_id,
        event_type=delivery.event_type,
        attempt=delivery.attempt,
        detail=dict(delivery.detail),
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _settings(state: GatewayState, auth: AuthenticatedRequest) -> RootConfig:
    """Return the caller's effective configuration, or the shipped defaults."""
    service = ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)
    for node_id in (auth.team_node_id, auth.scope.org_id):
        if not node_id:
            continue
        try:
            return (await service.resolve(node_id)).config
        except Exception:  # noqa: BLE001 — an unresolvable tree is a defaulted read
            continue
    return RootConfig()


@router.get("/ingress", response_model=IngressStatusView)
async def ingress_status(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    rejections: int = 5,
) -> IngressStatusView:
    """Return every receiver this deployment serves, and what it has done lately.

    Built by enumerating the *configured* sources and joining the ledger onto
    them, never the other way round. A listing built from the ledger would omit
    exactly the source this screen exists to show: the one that has never
    delivered anything.
    """
    if rejections < 0:
        raise bad_request("rejections cannot be negative")
    since = _utc_now() - timedelta(hours=TRANSIT_ACTIVITY_WINDOW_HOURS)
    since_this_week = _utc_now() - timedelta(hours=TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS)
    base = ""

    async with state.gateway.begin(auth.scope) as uow:
        activity = {
            row.source: row
            for row in await uow.transit.activity(direction=TransitDirection.INGRESS, since=since)
        }
        # A second, wider read rather than widening the one above: "is this
        # still arriving" and "how much has been arriving" are different
        # questions, and collapsing them onto one window would make `counts`
        # answer neither cleanly.
        weekly_activity = {
            row.source: row
            for row in await uow.transit.activity(
                direction=TransitDirection.INGRESS, since=since_this_week
            )
        }
        refused = await uow.transit.deliveries(
            TransitQuery(
                directions=(TransitDirection.INGRESS,),
                outcomes=(TransitOutcome.REJECTED, TransitOutcome.SHED),
                limit=DEFAULT_TRANSIT_PAGE_SIZE,
            )
        )
        samples = {
            name: await uow.transit.sample(name) for name in sorted(PROFILES) if name in activity
        }

    sources: list[IngressSourceStatusView] = []
    for name, profile in sorted(PROFILES.items()):
        seen = activity.get(name)
        last = seen.last_delivery if seen is not None else None
        sample = samples.get(name)
        sources.append(
            IngressSourceStatusView(
                source=name,
                path=f"/webhooks/{name}",
                url=f"{base}/webhooks/{name}",
                expects=profile.expects,
                verification=profile.verification,
                never_delivered=last is None,
                last_delivery_at="" if last is None else last.occurred_at.isoformat(),
                last_outcome="" if last is None else last.outcome.value,
                counts=(
                    {}
                    if seen is None
                    else {outcome.value: count for outcome, count in seen.counts.items()}
                ),
                week_count=(0 if name not in weekly_activity else weekly_activity[name].total),
                recent_rejections=[_view(row) for row in refused if row.source == name][
                    :rejections
                ],
                sample=(
                    None
                    if sample is None
                    else SampleView(
                        captured_at=sample.captured_at.isoformat(),
                        body=sample.body,
                        masking_policy=sample.masking_policy,
                        truncated=sample.truncated,
                    )
                ),
            )
        )
    return IngressStatusView(sources=sources)


@router.get("/deliveries", response_model=list[DeliveryView])
async def deliveries(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    direction: str = "",
    outcome: str = "",
    limit: int = DEFAULT_TRANSIT_PAGE_SIZE,
) -> list[DeliveryView]:
    """Return recent crossings, newest first, in either direction."""
    directions = () if not direction else (_direction(direction),)
    outcomes = () if not outcome else (_outcome(outcome),)
    async with state.gateway.begin(auth.scope) as uow:
        rows = await uow.transit.deliveries(
            TransitQuery(directions=directions, outcomes=outcomes, limit=limit)
        )
    return [_view(row) for row in rows]


@router.get("/rules", response_model=RulesView)
async def rules(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> RulesView:
    """Return the ordered rule set, with the catch-all always present and last.

    A deployment that has configured nothing gets the default set rather than an
    empty list, because "what happens to a delivery here" always has an answer
    and the screen has to be able to show it.
    """
    settings = await _settings(state, auth)
    rule_set = settings.transit.rule_set()
    return RulesView(
        rules=[
            RuleView(
                rule_id=rule.rule_id,
                sources=list(rule.sources),
                zones=list(rule.zones),
                criticalities=list(rule.criticalities),
                resources=list(rule.resource_ids),
                team=rule.team_node_id,
                action=rule.action,
                reason=rule.reason,
                is_catch_all=rule.is_catch_all,
            )
            for rule in rule_set.rules
        ]
    )


@router.post("/simulate", response_model=SimulationView)
async def simulate(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    body: Mapping[str, Any] = Body(default_factory=dict),
) -> SimulationView:
    """Return which rule would catch this delivery, where it would go, and what would happen.

    Takes either a pasted ``payload`` with its ``source``, or the
    ``delivery_id`` of a crossing already in the ledger. Both end in the same
    ``evaluate`` call the live ingress path makes — asserted by construction
    rather than by comparison, because there is only one implementation to call.
    """
    source = str(body.get("source") or "")
    payload = body.get("payload")
    delivery_id = str(body.get("delivery_id") or "")

    if delivery_id:
        async with state.gateway.begin(auth.scope) as uow:
            stored = await uow.transit.delivery(delivery_id)
        if stored is None:
            raise not_found(f"no delivery {delivery_id!r} is in this tenant's transit ledger")
        source = stored.source
        signals = Signals(
            source=stored.source,
            resource_id=stored.resource_id,
            team_node_id=stored.team_node_id or auth.team_node_id,
        )
        settings = await _settings(state, auth)
        match = evaluate(settings.transit.rule_set(), signals)
        return _simulated(
            match.rule.rule_id, match.action, match.team_node_id, match.reason, signals
        )

    if source not in PROFILES:
        raise bad_request(
            f"source must be one of {', '.join(sorted(PROFILES))}; a simulation against a "
            f"receiver this deployment does not serve would answer about nothing"
        )
    if not isinstance(payload, dict):
        raise bad_request("payload must be a JSON object, or pass a delivery_id instead")

    alert = adapter_for(PROFILES[source].source).normalise(
        RawAlert(payload=payload, received_at=_utc_now())
    )
    async with state.gateway.begin(auth.scope) as uow:
        resources = await uow.estate.query(EstateQuery(limit=_estate_page()))
    resolution = resolve_alert(alert, resources=resources)
    resolved = resolution.resolved
    zone = resolved.zone if resolved is not None else ""
    if not zone and resolution.unresolved is not None:
        zone = resolution.unresolved.zone
    signals = Signals(
        source=source,
        zone=zone,
        criticality=alert.severity.value,
        resource_id=resolved.resource_id if resolved is not None else "",
        team_node_id=auth.team_node_id,
    )
    settings = await _settings(state, auth)
    match = evaluate(settings.transit.rule_set(), signals)
    return _simulated(match.rule.rule_id, match.action, match.team_node_id, match.reason, signals)


def _simulated(
    rule_id: str, action: str, team: str, reason: str, signals: Signals
) -> SimulationView:
    """Return the simulation answer, with what the matchers actually saw."""
    return SimulationView(
        rule_id=rule_id,
        action=action,
        team=team,
        reason=reason,
        signals={
            "source": signals.source,
            "zone": signals.zone,
            "criticality": signals.criticality,
            "resource_id": signals.resource_id,
        },
    )


@router.get("/destinations", response_model=DestinationsView)
async def destinations(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DestinationsView:
    """Return every declared destination, and why one cannot be configured.

    A deployment whose catalogue holds nothing that can deliver a message says
    so once, here, rather than rendering rows that would silently never send.
    """
    settings = await _settings(state, auth)
    declared = declared_destinations(settings, channels=delivery_channels(settings))
    return DestinationsView(
        destinations=[
            DestinationView(
                destination_id=each.destination_id,
                channel=each.channel,
                events=list(each.events),
                detail=each.detail,
                enabled=each.enabled,
                masking_policy=each.masking_policy,
                unconfigurable_reason=each.unconfigurable_reason,
            )
            for each in declared
        ],
        events=list(DELIVERY_EVENTS),
        unconfigurable_reason=("" if delivery_channels(settings) else NO_DELIVERY_CHANNEL_REASON),
    )


@router.post("/deliveries/{delivery_id}/resend", response_model=DeliveryView)
async def resend_delivery(
    delivery_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> DeliveryView:
    """Send a failed outbound delivery again, and record that a person asked.

    A re-send puts a report in front of somebody, so it is a human act and is
    audited like every other one — Article III. Refused for a delivery that
    did not fail: re-sending a message the destination already accepted would
    be this deployment producing a duplicate nobody asked for.
    """
    async with state.gateway.begin(auth.scope) as uow:
        stored = await uow.transit.delivery(delivery_id)
    if stored is None or stored.direction is not TransitDirection.OUTBOUND:
        raise not_found(f"no delivery {delivery_id!r} is in this tenant's transit ledger")
    if stored.outcome is not TransitOutcome.FAILED:
        raise bad_request(
            f"delivery {delivery_id!r} did not fail — its outcome is "
            f"{stored.outcome.value!r}, and re-sending it would produce a duplicate"
        )

    settings = await _settings(state, auth)
    dispatcher = DeliveryDispatcher(
        gateway=state.gateway,
        scope=auth.scope,
        settings=settings,
        channels=delivery_channels(settings),
        clock=_utc_now,
    )
    return _view(await resend(dispatcher, stored, actor_id=auth.principal_id))


def _direction(value: str) -> TransitDirection:
    try:
        return TransitDirection(value)
    except ValueError as unknown:
        raise bad_request(
            f"direction must be one of {', '.join(d.value for d in TransitDirection)}"
        ) from unknown


def _outcome(value: str) -> TransitOutcome:
    try:
        return TransitOutcome(value)
    except ValueError as unknown:
        raise bad_request(
            f"outcome must be one of {', '.join(o.value for o in TransitOutcome)}"
        ) from unknown


def _estate_page() -> int:
    """Return the estate page a simulation resolves against.

    The same bound the live path uses, imported here rather than repeated so
    the two cannot resolve against differently sized pages and disagree.
    """
    from config.constants.estate import MAX_ESTATE_PAGE_SIZE

    return MAX_ESTATE_PAGE_SIZE


__all__ = [
    "DeliveryView",
    "DestinationsView",
    "IngressStatusView",
    "RulesView",
    "SimulationView",
    "router",
]
