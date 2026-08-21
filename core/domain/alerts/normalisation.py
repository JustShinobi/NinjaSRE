"""One adapter per source, and the same shape out of all of them.

An alert is the only input the pipeline is given, and every stage after intake
reads it: planning scores against the source and the components, the runtime is
told what to investigate, delivery says what fired. Letting each of those parse
a vendor payload for itself is how six places end up disagreeing about which
service the alert was for.

So parsing happens once, here, and the rest of the system sees
``NormalisedAlert``. Two properties make that work in production:

**Nothing raises.** A payload missing every field an adapter hoped for produces
an alert with those fields empty, not an exception. The alert that breaks intake
is the one nobody looks at, and it always arrives at three in the morning.

**Detection is a predicate per source, not a guess.** Grafana's unified alerting
sends a payload that satisfies the Alertmanager shape, so each predicate names
what makes its source distinguishable rather than relying on the order the
adapters happen to be tried in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, Protocol

from core.domain.alerts.sources import ALERT_SOURCES, AlertSource
from core.domain.alerts.window import as_utc


class Severity(StrEnum):
    """How bad the sender said it was, on one scale.

    Six vendors use six vocabularies — ``P1``, ``critical``, ``error``,
    ``alerting`` — and scoring, routing, and the answer keys all need one. The
    mapping is per adapter; this is what they map onto.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


#: Vendor severity words that mean the same thing, lower-cased. Shared because
#: several vendors use the same words, and a per-adapter copy would drift.
_SEVERITY_WORDS: Final[Mapping[str, Severity]] = {
    "critical": Severity.CRITICAL,
    "crit": Severity.CRITICAL,
    "fatal": Severity.CRITICAL,
    "disaster": Severity.CRITICAL,
    "p1": Severity.CRITICAL,
    "sev1": Severity.CRITICAL,
    "error": Severity.HIGH,
    "high": Severity.HIGH,
    "major": Severity.HIGH,
    "alerting": Severity.HIGH,
    "p2": Severity.HIGH,
    "sev2": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "warn": Severity.MEDIUM,
    "medium": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "p3": Severity.MEDIUM,
    "sev3": Severity.MEDIUM,
    "low": Severity.LOW,
    "minor": Severity.LOW,
    "p4": Severity.LOW,
    "p5": Severity.LOW,
    "sev4": Severity.LOW,
    "info": Severity.INFO,
    "information": Severity.INFO,
    "debug": Severity.INFO,
    "success": Severity.INFO,
    "ok": Severity.INFO,
}

#: Label and tag keys that name a component, in the order a report should read
#: them. Deduplication downstream keeps the first occurrence, so the order is
#: what decides whether a report says "checkout" or "pod-7f4c".
_COMPONENT_KEYS: Final[tuple[str, ...]] = (
    "service",
    "app",
    "application",
    "deployment",
    "statefulset",
    "job",
    "namespace",
    "cluster",
    "container",
    "pod",
    "instance",
    "host",
    "node",
    "database",
    "queue",
)


@dataclass(frozen=True, slots=True)
class RawAlert:
    """What arrived, before anything interpreted it.

    Both fields are optional and both may be present: a chat integration sends
    text, a webhook sends JSON, and an ingestion surface that has both sends
    both. ``source_hint`` is what the transport already knows — the webhook
    route it arrived on — and it wins over shape detection, because a route is
    a fact and a shape is an inference.
    """

    text: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    source_hint: str = ""
    received_at: datetime | None = None

    def at(self) -> datetime:
        """Return when this arrived, defaulting to now."""
        return as_utc(self.received_at) if self.received_at is not None else datetime.now(UTC)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this input."""
        return {
            "text": self.text,
            "payload": dict(self.payload),
            "source_hint": self.source_hint,
            "received_at": self.received_at.isoformat() if self.received_at else "",
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> RawAlert:
        """Return the input a stored record describes."""
        stamp = str(record.get("received_at", ""))
        return cls(
            text=str(record.get("text", "")),
            payload=dict(record.get("payload") or {}),
            source_hint=str(record.get("source_hint", "")),
            received_at=datetime.fromisoformat(stamp) if stamp else None,
        )


@dataclass(frozen=True, slots=True)
class NormalisedAlert:
    """The same alert, in the shape every stage after intake reads.

    ``resolved`` matters more than it looks. A resolved notification arriving
    while an investigation is open is the strongest evidence available that the
    incident ended, and losing it in normalisation means the run keeps
    investigating something that stopped.
    """

    alert_source: AlertSource
    alert_name: str = ""
    severity: Severity = Severity.UNKNOWN
    summary: str = ""
    description: str = ""
    components: tuple[str, ...] = ()
    error_text: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    reference: str = ""
    resolved: bool = False
    labels: Mapping[str, str] = field(default_factory=dict)
    #: What the sender called the group this alert is in, when it groups at all.
    #: Kept rather than re-derived, because the grouping decision belongs to the
    #: system that made it: a deployment that disagreed with its own Alertmanager
    #: about which notifications are one problem would undo the grouping the
    #: operator configured. Empty for a source with no such concept.
    group_key: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this alert."""
        return {
            "alert_source": self.alert_source.value,
            "alert_name": self.alert_name,
            "severity": self.severity.value,
            "summary": self.summary,
            "description": self.description,
            "components": list(self.components),
            "error_text": self.error_text,
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "ended_at": self.ended_at.isoformat() if self.ended_at else "",
            "reference": self.reference,
            "resolved": self.resolved,
            "labels": dict(self.labels),
            "group_key": self.group_key,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> NormalisedAlert:
        """Return the alert a stored record describes."""
        return cls(
            alert_source=AlertSource(record["alert_source"]),
            alert_name=str(record.get("alert_name", "")),
            severity=Severity(record.get("severity", Severity.UNKNOWN.value)),
            summary=str(record.get("summary", "")),
            description=str(record.get("description", "")),
            components=tuple(str(item) for item in record.get("components") or ()),
            error_text=str(record.get("error_text", "")),
            started_at=_moment(record.get("started_at")),
            ended_at=_moment(record.get("ended_at")),
            reference=str(record.get("reference", "")),
            resolved=bool(record.get("resolved", False)),
            labels={str(key): str(value) for key, value in (record.get("labels") or {}).items()},
            group_key=str(record.get("group_key", "")),
        )


class AlertAdapter(Protocol):
    """One source's payload shape, recognised and translated."""

    @property
    def source(self) -> AlertSource:
        """Return the source this adapter speaks for."""

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` came from this source."""

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return ``raw`` in the shape every stage after intake reads."""


# -- reading a payload without trusting it ------------------------------------


def _mapping(value: object) -> Mapping[str, Any]:
    """Return ``value`` as a mapping, or an empty one if it is not."""
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> Sequence[Any]:
    """Return ``value`` as a sequence, treating a string as not being one."""
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return ()


def _text(value: object) -> str:
    """Return ``value`` as trimmed text, or empty for anything unprintable."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    return ""


def _first(source: Mapping[str, Any], *keys: str) -> str:
    """Return the first of ``keys`` present in ``source`` with a non-empty value."""
    for key in keys:
        found = _text(source.get(key))
        if found:
            return found
    return ""


def _strings(value: object) -> tuple[str, ...]:
    """Return ``value`` as a tuple of non-empty strings, whatever shape it came in.

    Datadog sends tags as a comma-separated string and Opsgenie sends them as a
    list; both mean the same thing and neither is worth a separate code path.
    """
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(found for item in _items(value) if (found := _text(item)))


def _moment(value: object) -> datetime | None:
    """Return the instant ``value`` names, or ``None`` when it names none.

    Alertmanager sends ``0001-01-01T00:00:00Z`` for the end of a firing alert,
    which parses cleanly and means "not ended". Treating it as a real timestamp
    would produce a window that closed two thousand years ago.
    """
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, int | float) and value > 0:
        # Datadog sends milliseconds; everything else that sends a number sends
        # seconds. The boundary is far enough in the future to be unambiguous.
        seconds = float(value) / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC)
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.year <= 1:
        return None
    return as_utc(parsed)


def _severity(*candidates: str) -> Severity:
    """Return the first candidate that names a severity, or ``UNKNOWN``."""
    for candidate in candidates:
        found = _SEVERITY_WORDS.get(candidate.strip().lower())
        if found is not None:
            return found
    return Severity.UNKNOWN


def _labels(source: Mapping[str, Any]) -> dict[str, str]:
    """Return ``source`` flattened to string keys and values, blanks dropped."""
    return {str(key): _text(value) for key, value in source.items() if _text(value) and _text(key)}


def _tag_labels(tags: Iterable[str]) -> dict[str, str]:
    """Return ``key:value`` tags as a mapping, ignoring tags with no value."""
    found: dict[str, str] = {}
    for tag in tags:
        key, separator, value = tag.partition(":")
        if separator and key.strip() and value.strip():
            found.setdefault(key.strip(), value.strip())
    return found


def _components(*sources: Mapping[str, str]) -> tuple[str, ...]:
    """Return the component names across ``sources``, first occurrence kept."""
    found: dict[str, None] = {}
    for source in sources:
        for key in _COMPONENT_KEYS:
            value = source.get(key, "").strip()
            if value:
                found.setdefault(value, None)
    return tuple(found)


def _unique(*values: str) -> tuple[str, ...]:
    """Return the non-empty values, deduplicated, order preserved."""
    found: dict[str, None] = {}
    for value in values:
        if value.strip():
            found.setdefault(value.strip(), None)
    return tuple(found)


# -- the adapters -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlertmanagerAdapter:
    """Prometheus Alertmanager's grouped webhook.

    A group carries several alerts. The first firing one is what the
    investigation is about; the rest become components and labels, because an
    alert group is one incident seen from several instances.
    """

    source: AlertSource = AlertSource.ALERTMANAGER

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` is an Alertmanager group and not a Grafana one."""
        payload = raw.payload
        if not _items(payload.get("alerts")):
            return False
        if _GRAFANA_MARKERS & set(payload):
            return False
        return "receiver" in payload or "groupKey" in payload or "commonLabels" in payload

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the group's leading alert, with the group's labels merged in.

        The leading alert decides the headline — its labels, its window, its
        annotations — but every member's own component is kept, not only the
        leading one's. A group of two members firing on two different hosts
        is one incident about two hosts, and a component list that named only
        the first would leave the second one invisible to whoever reads the
        incident afterwards.
        """
        payload = raw.payload
        alerts = [_mapping(item) for item in _items(payload.get("alerts"))]
        firing = next((item for item in alerts if _first(item, "status") == "firing"), None)
        leading = firing if firing is not None else (alerts[0] if alerts else {})

        labels = {
            **_labels(_mapping(payload.get("commonLabels"))),
            **_labels(_mapping(leading.get("labels"))),
        }
        annotations = _labels(_mapping(leading.get("annotations")))
        status = _first(leading, "status") or _first(payload, "status")
        member_labels = tuple(_labels(_mapping(member.get("labels"))) for member in alerts)

        return NormalisedAlert(
            alert_source=self.source,
            alert_name=labels.get("alertname", "") or _first(payload, "groupKey"),
            severity=_severity(labels.get("severity", "")),
            summary=annotations.get("summary", "") or annotations.get("title", ""),
            description=annotations.get("description", "") or annotations.get("message", ""),
            components=_components(labels, *member_labels),
            error_text=annotations.get("description", ""),
            started_at=_moment(leading.get("startsAt")),
            ended_at=_moment(leading.get("endsAt")),
            reference=_first(leading, "generatorURL") or _first(payload, "externalURL"),
            resolved=status == "resolved",
            labels=labels,
            group_key=_first(payload, "groupKey"),
        )


#: Fields only Grafana puts on an otherwise Alertmanager-shaped body. Grafana's
#: unified alerting is deliberately Alertmanager-compatible, so the two are told
#: apart by what Grafana adds rather than by trying the adapters in some order.
_GRAFANA_MARKERS: Final[frozenset[str]] = frozenset({"orgId", "ruleUrl", "ruleName", "evalMatches"})


@dataclass(frozen=True, slots=True)
class GrafanaAdapter:
    """Grafana alerting, unified and legacy.

    Two payload shapes behind one adapter, because they are one product and a
    deployment may send either depending on its version.
    """

    source: AlertSource = AlertSource.GRAFANA

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries a marker only Grafana sends."""
        return bool(_GRAFANA_MARKERS & set(raw.payload))

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the alert, reading the unified shape first and the legacy one after."""
        payload = raw.payload
        alerts = [_mapping(item) for item in _items(payload.get("alerts"))]
        leading = alerts[0] if alerts else {}
        labels = {
            **_labels(_mapping(payload.get("commonLabels"))),
            **_labels(_mapping(leading.get("labels"))),
        }
        annotations = _labels(_mapping(leading.get("annotations")))

        # Legacy Grafana names the rule and lists the series that matched it;
        # unified Grafana carries labels instead. Neither is present in both.
        matched = [_mapping(item) for item in _items(payload.get("evalMatches"))]
        matched_labels = {
            key: value
            for item in matched
            for key, value in _labels(_mapping(item.get("tags"))).items()
        }

        state = _first(payload, "state", "status") or _first(leading, "status")
        return NormalisedAlert(
            alert_source=self.source,
            alert_name=labels.get("alertname", "") or _first(payload, "ruleName", "title"),
            severity=_severity(labels.get("severity", ""), state),
            summary=annotations.get("summary", "") or _first(payload, "title", "message"),
            description=annotations.get("description", "") or _first(payload, "message"),
            components=_components(labels, matched_labels),
            error_text=_first(payload, "message"),
            started_at=_moment(leading.get("startsAt")),
            ended_at=_moment(leading.get("endsAt")),
            reference=_first(payload, "ruleUrl", "externalURL") or _first(leading, "generatorURL"),
            resolved=state in {"ok", "resolved"},
            labels={**matched_labels, **labels},
        )


@dataclass(frozen=True, slots=True)
class PagerDutyAdapter:
    """PagerDuty's v3 incident webhook."""

    source: AlertSource = AlertSource.PAGERDUTY

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries a PagerDuty event envelope."""
        event = _mapping(raw.payload.get("event"))
        return bool(event) and ("data" in event or "event_type" in event)

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the incident the event describes."""
        event = _mapping(raw.payload.get("event"))
        data = _mapping(event.get("data"))
        service = _first(_mapping(data.get("service")), "summary", "name")
        priority = _first(_mapping(data.get("priority")), "summary", "name")
        status = _first(data, "status")

        labels = {"status": status, "urgency": _first(data, "urgency"), "priority": priority}
        if service:
            labels["service"] = service

        return NormalisedAlert(
            alert_source=self.source,
            alert_name=_first(data, "title", "summary"),
            severity=_severity(priority, _first(data, "urgency")),
            summary=_first(data, "title", "summary"),
            description=_first(data, "description"),
            components=_unique(service),
            error_text=_first(data, "description"),
            started_at=_moment(data.get("created_at")) or _moment(event.get("occurred_at")),
            ended_at=_moment(data.get("resolved_at")),
            reference=_first(data, "html_url", "self"),
            resolved=status == "resolved" or _first(event, "event_type").endswith("resolved"),
            labels={key: value for key, value in labels.items() if value},
        )


@dataclass(frozen=True, slots=True)
class DatadogAdapter:
    """Datadog's monitor webhook.

    The body is operator-templated, so the adapter reads the field names
    Datadog's own default template emits and treats everything else as absent.
    """

    source: AlertSource = AlertSource.DATADOG

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries Datadog's monitor fields."""
        payload = raw.payload
        return "alert_id" in payload or "alert_title" in payload or "alert_transition" in payload

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the monitor alert, with ``key:value`` tags read as labels."""
        payload = raw.payload
        tags = _tag_labels(_strings(payload.get("tags")))
        transition = _first(payload, "alert_transition", "alert_type")

        return NormalisedAlert(
            alert_source=self.source,
            alert_name=_first(payload, "alert_title", "title", "alert_metric"),
            severity=_severity(_first(payload, "priority", "alert_type"), tags.get("severity", "")),
            summary=_first(payload, "alert_title", "title"),
            description=_first(payload, "body", "text_only_msg"),
            components=_components(tags),
            error_text=_first(payload, "body", "text_only_msg"),
            started_at=_moment(payload.get("date")) or _moment(payload.get("last_updated")),
            ended_at=None,
            reference=_first(payload, "link", "url", "event_msg"),
            resolved=transition.strip().lower() in {"recovered", "resolved", "success"},
            labels={**tags, "alert_id": _first(payload, "alert_id")}
            if tags or _first(payload, "alert_id")
            else {},
        )


@dataclass(frozen=True, slots=True)
class SentryAdapter:
    """Sentry's issue and error webhooks, current and legacy."""

    source: AlertSource = AlertSource.SENTRY

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries a Sentry issue, error, or legacy body."""
        payload = raw.payload
        data = _mapping(payload.get("data"))
        return "culprit" in payload or "issue" in data or "error" in data

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the issue, whichever of the three shapes carried it."""
        payload = raw.payload
        data = _mapping(payload.get("data"))
        issue = _mapping(data.get("issue")) or _mapping(data.get("error")) or payload

        project = _first(_mapping(issue.get("project")), "slug", "name") or _first(
            payload, "project", "project_slug", "project_name"
        )
        level = _first(issue, "level") or _first(_mapping(payload.get("event")), "level")
        culprit = _first(issue, "culprit") or _first(payload, "culprit")

        labels = {"project": project, "level": level, "culprit": culprit}
        return NormalisedAlert(
            alert_source=self.source,
            alert_name=_first(issue, "title", "metadata_type") or _first(payload, "message"),
            severity=_severity(level),
            summary=_first(issue, "title") or _first(payload, "message"),
            description=culprit,
            components=_unique(project),
            error_text=_first(issue, "title") or _first(payload, "message"),
            started_at=_moment(issue.get("firstSeen")) or _moment(issue.get("lastSeen")),
            ended_at=None,
            reference=_first(issue, "web_url", "permalink", "url") or _first(payload, "url"),
            resolved=_first(issue, "status") == "resolved",
            labels={key: value for key, value in labels.items() if value},
        )


@dataclass(frozen=True, slots=True)
class OpsgenieAdapter:
    """Opsgenie's alert-action webhook."""

    source: AlertSource = AlertSource.OPSGENIE

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries an Opsgenie alert envelope."""
        alert = _mapping(raw.payload.get("alert"))
        return "alertId" in alert or "tinyId" in alert

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the alert the action was taken on."""
        payload = raw.payload
        alert = _mapping(payload.get("alert"))
        tags = _tag_labels(_strings(alert.get("tags")))
        details = _labels(_mapping(alert.get("details")))
        action = _first(payload, "action")

        entity = _first(alert, "entity")
        labels = {**tags, **details}
        if _first(alert, "team"):
            labels.setdefault("team", _first(alert, "team"))

        return NormalisedAlert(
            alert_source=self.source,
            alert_name=_first(alert, "message", "alias"),
            severity=_severity(_first(alert, "priority"), tags.get("severity", "")),
            summary=_first(alert, "message"),
            description=_first(alert, "description"),
            components=_unique(entity, *_components(labels)),
            error_text=_first(alert, "description"),
            started_at=_moment(alert.get("createdAt")) or _moment(payload.get("createdAt")),
            ended_at=None,
            reference=_first(alert, "alertId", "tinyId"),
            resolved=action.strip().lower() in {"close", "closed", "resolve", "resolved"},
            labels=labels,
        )


@dataclass(frozen=True, slots=True)
class GenericWebhookAdapter:
    """Any JSON body nobody recognised.

    It still has fields, and the conventional ones — a title, a severity, a
    service — are worth reading. An unrecognised payload investigated from its
    title beats an unrecognised payload dropped.
    """

    source: AlertSource = AlertSource.WEBHOOK

    def matches(self, raw: RawAlert) -> bool:
        """Return whether ``raw`` carries a payload at all."""
        return bool(raw.payload)

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return whatever the conventional field names yielded."""
        payload = raw.payload
        labels = _labels(payload)
        status = _first(payload, "status", "state")

        return NormalisedAlert(
            alert_source=self.source,
            alert_name=_first(payload, "alert_name", "alertname", "name", "title", "summary"),
            severity=_severity(_first(payload, "severity", "level", "priority")),
            summary=_first(payload, "summary", "title", "message", "text"),
            description=_first(payload, "description", "detail", "body", "message"),
            components=_components(labels),
            error_text=_first(payload, "error", "message", "description"),
            started_at=_moment(payload.get("started_at"))
            or _moment(payload.get("startsAt"))
            or _moment(payload.get("timestamp")),
            ended_at=_moment(payload.get("ended_at")) or _moment(payload.get("endsAt")),
            reference=_first(payload, "url", "link", "id"),
            resolved=status.strip().lower() in {"resolved", "ok", "closed"},
            labels=labels,
        )


@dataclass(frozen=True, slots=True)
class PlainTextAdapter:
    """A sentence somebody typed. The adapter of last resort, and it always matches.

    It extracts almost nothing on purpose. Intake's model call is what turns
    prose into fields, and guessing a severity from a chat message here would
    put a number on something nobody measured.
    """

    source: AlertSource = AlertSource.PLAIN_TEXT

    def matches(self, raw: RawAlert) -> bool:
        """Return ``True``: every input can be read as text."""
        return True

    def normalise(self, raw: RawAlert) -> NormalisedAlert:
        """Return the text as the summary, with nothing inferred from it."""
        text = raw.text.strip()
        headline = text.splitlines()[0].strip() if text else ""
        return NormalisedAlert(
            alert_source=self.source,
            alert_name=headline[:120],
            summary=headline,
            description=text,
            error_text=text,
        )


#: One adapter per source, in detection order. Grafana precedes Alertmanager so
#: the shared shape is attributed to whichever predicate is the more specific,
#: and the two fallbacks come last because both would match almost anything.
ADAPTERS: Final[tuple[AlertAdapter, ...]] = (
    GrafanaAdapter(),
    AlertmanagerAdapter(),
    PagerDutyAdapter(),
    DatadogAdapter(),
    SentryAdapter(),
    OpsgenieAdapter(),
    GenericWebhookAdapter(),
    PlainTextAdapter(),
)

_BY_SOURCE: Final[Mapping[AlertSource, AlertAdapter]] = {
    adapter.source: adapter for adapter in ADAPTERS
}


def adapter_for(source: AlertSource) -> AlertAdapter:
    """Return the adapter that speaks for ``source``."""
    return _BY_SOURCE[source]


def detect_source(raw: RawAlert) -> AlertSource:
    """Return which source ``raw`` came from.

    A transport that already knows wins: ``source_hint`` is the route the
    payload arrived on, which is a fact, and shape detection is an inference.
    """
    hinted = raw.source_hint.strip().lower()
    for source in ALERT_SOURCES:
        if source.value == hinted:
            return source

    for adapter in ADAPTERS:
        if adapter.matches(raw):
            return adapter.source
    return AlertSource.PLAIN_TEXT


def normalise(raw: RawAlert) -> NormalisedAlert:
    """Return ``raw`` in the shape every stage after intake reads.

    Never raises. An adapter that finds nothing it hoped for returns an alert
    with those fields empty, because the alert that breaks intake is the one
    nobody looks at.
    """
    source = detect_source(raw)
    normalised = adapter_for(source).normalise(raw)

    # An adapter that recognised the payload but found no headline in it leaves
    # the run with nothing to investigate. The raw text is a worse summary than
    # a parsed one and a much better one than an empty string.
    if not normalised.summary and raw.text.strip():
        headline = raw.text.strip().splitlines()[0].strip()
        return NormalisedAlert(
            alert_source=normalised.alert_source,
            alert_name=normalised.alert_name or headline[:120],
            severity=normalised.severity,
            summary=headline,
            description=normalised.description or raw.text.strip(),
            components=normalised.components,
            error_text=normalised.error_text or raw.text.strip(),
            started_at=normalised.started_at,
            ended_at=normalised.ended_at,
            reference=normalised.reference,
            resolved=normalised.resolved,
            labels=normalised.labels,
            group_key=normalised.group_key,
        )
    return normalised


__all__ = [
    "ADAPTERS",
    "AlertAdapter",
    "AlertmanagerAdapter",
    "GenericWebhookAdapter",
    "GrafanaAdapter",
    "NormalisedAlert",
    "PlainTextAdapter",
    "RawAlert",
    "Severity",
    "adapter_for",
    "detect_source",
    "normalise",
]
