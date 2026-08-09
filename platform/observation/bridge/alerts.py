"""An alert somebody else raised, arriving as an incident of ours — correlated.

``platform/incidents/ingestion.py`` already turns an alert into an
``IncidentRaise``. What it cannot do is decide *which estate resource* the alert
is about, because that needs the label rules and the estate, and both belong to
this package. So this module is the join and nothing more: it correlates, and
then it calls the one path that already exists.

That is deliberate to the point of being enforced. A structural test asserts
this module constructs no ``Incident`` and no ``IncidentRaise`` of its own,
because "we go through the lifecycle" is the kind of claim that stays true until
somebody adds a fast path for one field, and Alertmanager is the source most
likely to tempt one — its payload already looks like an incident.

**An uncorrelated alert still opens an incident.** Somebody's monitoring decided
this was worth sending. Dropping it because this deployment cannot name the
resource would be the system deciding it knows better than the operator's own
alerting, and it would do so silently. The incident is opened and labelled
uncorrelated, which is a state a console can show and an operator can act on.

**The upstream's grouping is respected.** Alertmanager already decided which
alerts are one thing; re-deriving that here would mean this deployment
disagreeing with the system that will eventually send the resolution. When a
group key is present it is what the incident correlates on, so a group of twenty
alerts is one incident with twenty firings on it.

**A resolution closes, and says who closed it.** Recorded as source-resolved
rather than as "the condition cleared", because those are different facts: one
means our own recovery condition held, and the other means somebody else's
system says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Final

from config.constants.notifications import SEVERITY_HIGH
from platform.incidents.ingestion import raise_for_alert, resolution_key
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.observability.logging import get_logger
from platform.observation.bridge.mapping import EstateIndex, LabelRule, choose_resource
from platform.persistence.ports.incident_store import Incident, IncidentState

logger = get_logger(__name__)

#: What the source calls an alert that is currently true.
ALERT_STATUS_FIRING: Final = "firing"

#: What it calls one that has stopped being true.
ALERT_STATUS_RESOLVED: Final = "resolved"

#: What an incident's close reason says when the system that raised it says it
#: is over. Distinct from our own recovery condition holding, because an operator
#: reading a closed incident is asking which of the two happened.
SOURCE_RESOLVED_REASON: Final = "the source that raised it reported it resolved"

#: The label that says whether the alert reached an estate resource. On the
#: incident rather than only in a log, because "we could not tell what this is
#: about" is something a console has to be able to show.
CORRELATED_LABEL: Final = "correlated"

#: The label that says what the incident correlates on — the upstream's grouping
#: or its per-alert fingerprint.
GROUPED_BY_LABEL: Final = "grouped_by"


@dataclass(frozen=True, slots=True)
class IncomingAlert:
    """One alert as the source sent it, before anything of ours has been decided."""

    source: str
    fingerprint: str
    alert_name: str
    status: str = ALERT_STATUS_FIRING
    #: The source's own grouping. Empty when it sent none, which is when the
    #: fingerprint is what the incident correlates on.
    group_key: str = ""
    summary: str = ""
    description: str = ""
    severity: str = SEVERITY_HIGH
    labels: Mapping[str, str] = field(default_factory=dict)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    #: Where the alert says it came from — a Prometheus expression URL, usually.
    #: Carried onto the incident's evidence so a responder can see the rule.
    generator_url: str = ""

    @property
    def is_firing(self) -> bool:
        """Return whether this alert is currently true."""
        return self.status != ALERT_STATUS_RESOLVED

    @property
    def grouping_fingerprint(self) -> str:
        """Return what this alert correlates on: the source's grouping, or its own."""
        return self.group_key or self.fingerprint

    @property
    def grouped_by(self) -> str:
        """Return which of the two the correlation used."""
        return "group_key" if self.group_key else "fingerprint"


@dataclass(frozen=True, slots=True)
class AlertCorrelation:
    """Which estate resource an alert is about, or why nothing could be said."""

    resource_id: str = ""
    rule_id: str = ""
    reason: str = ""

    @property
    def correlated(self) -> bool:
        """Return whether the alert reached a resource."""
        return bool(self.resource_id)


@dataclass(frozen=True, slots=True)
class AlertResolution:
    """What a resolution notification closes, and how it is recorded."""

    correlation_key: str
    reason: str
    actor: str
    state: IncidentState = IncidentState.RESOLVED


def correlate(
    labels: Mapping[str, str],
    *,
    rules: Sequence[LabelRule],
    estate: EstateIndex,
) -> AlertCorrelation:
    """Return the estate resource ``labels`` name, or why none could be found.

    The same label rules the series mapping uses. An alert is a label set and a
    series is a label set, and giving the two separate rule sets would mean an
    operator keeping two things in step that describe one convention.
    """
    reasons: list[str] = []
    for rule in rules:
        if not rule.applies_to_labels(labels):
            continue
        missing = rule.missing_labels_in(labels)
        if missing:
            reasons.append(f"rule {rule.rule_id!r} needs the label(s) {', '.join(missing)}")
            continue
        pattern = rule.pattern_for_labels(labels)
        if not pattern:
            continue
        chosen = choose_resource(
            estate.resolve(pattern, kind=rule.resource_kind, integration=rule.integration)
        )
        if chosen is None:
            reasons.append(
                f"rule {rule.rule_id!r} resolved to {pattern!r}, which matches no single "
                f"resource this estate holds"
            )
            continue
        return AlertCorrelation(resource_id=chosen.resource_id, rule_id=rule.rule_id)

    return AlertCorrelation(
        reason=(
            "; ".join(reasons)
            or "no declared label rule recognises this alert's labels, so the incident "
            "names the source rather than a resource"
        )
    )


def raise_for_incoming_alert(
    alert: IncomingAlert,
    *,
    rules: Sequence[LabelRule],
    estate: EstateIndex,
    team_node_id: str = "",
) -> IncidentRaise:
    """Return the raise ``alert`` describes, correlated to the estate where it can be.

    Delegates the construction to ``platform.incidents.ingestion`` so that there
    is one place an alert becomes an incident. What is added here is the subject
    — the estate resource rather than the alert's own name — and the two labels
    that say whether correlation succeeded and what the incident groups on.
    """
    found = correlate(alert.labels, rules=rules, estate=estate)
    request = raise_for_alert(
        source=alert.source,
        fingerprint=alert.grouping_fingerprint,
        alert_name=alert.alert_name,
        summary=alert.summary,
        description=alert.description,
        severity=alert.severity,
        components=(found.resource_id,) if found.correlated else (),
        team_node_id=team_node_id,
        reference=alert.generator_url,
    )
    if not found.correlated:
        logger.info(
            "bridge.alert_uncorrelated",
            source=alert.source,
            alert=alert.alert_name,
            reason=found.reason,
        )
    return replace(
        request,
        labels={
            **request.labels,
            CORRELATED_LABEL: "yes" if found.correlated else "no",
            GROUPED_BY_LABEL: alert.grouped_by,
            "rule": found.rule_id or found.reason,
        },
    )


def resolution_for(alert: IncomingAlert) -> AlertResolution:
    """Return what ``alert``'s resolution closes.

    Raises ``ValueError`` for an alert that is still firing. Closing an incident
    because a *firing* notification arrived would be the worst bug this module
    could have, and a caller that mixed the two up should find out here rather
    than from an operator whose incident list emptied itself.
    """
    if alert.is_firing:
        raise ValueError(
            f"{alert.alert_name!r} from {alert.source!r} is firing, not resolved. A "
            f"resolution closes an incident, and closing one because a firing alert "
            f"arrived is the failure this refusal exists to prevent."
        )
    return AlertResolution(
        correlation_key=_resolution_key(alert),
        reason=f"{SOURCE_RESOLVED_REASON}: {alert.source}",
        actor=f"source:{alert.source}",
    )


async def apply_resolution(
    lifecycle: IncidentLifecycle,
    resolution: AlertResolution,
    *,
    now: datetime,
) -> Incident | None:
    """Close the incident ``resolution`` refers to, or return ``None`` if there is none.

    ``None`` rather than an error. A deployment that started after the alert
    fired never opened an incident for it, and a resolution arriving for nothing
    is an ordinary consequence of that rather than a fault.
    """
    existing = await lifecycle.store.open_for(resolution.correlation_key)
    if existing is None:
        logger.info("bridge.resolution_without_incident", key=resolution.correlation_key)
        return None
    return await lifecycle.close(
        existing.incident_id,
        reason=resolution.reason,
        actor=resolution.actor,
        state=resolution.state,
        now=now,
    )


def _resolution_key(alert: IncomingAlert) -> str:
    """Return the correlation key a resolution closes.

    Derived through the same ingestion module the raise goes through, so the
    firing and the resolution cannot come to spell the key differently — which
    would leave an incident open for ever while the operator watched the
    upstream go green.
    """
    return resolution_key(source=alert.source, fingerprint=alert.grouping_fingerprint)


__all__ = [
    "ALERT_STATUS_FIRING",
    "ALERT_STATUS_RESOLVED",
    "CORRELATED_LABEL",
    "GROUPED_BY_LABEL",
    "SOURCE_RESOLVED_REASON",
    "AlertCorrelation",
    "AlertResolution",
    "IncomingAlert",
    "apply_resolution",
    "correlate",
    "raise_for_incoming_alert",
    "resolution_for",
]
