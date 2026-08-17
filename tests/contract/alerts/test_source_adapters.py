"""One real payload per source, and the same fields out of all of them.

These are contract tests rather than unit tests because the thing under test is
an agreement with somebody else's product: the body Alertmanager actually
posts, not the body this repository would like it to post. Each fixture below
is a payload of the shape the vendor documents, trimmed of the fields nothing
reads.

The suite asserts three things per source — that detection places it, that the
fields an investigation needs come out, and that a payload stripped to almost
nothing still normalises rather than raising. The third is the one that matters
at three in the morning.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, Severity, normalise
from core.domain.alerts.sources import ALERT_SOURCES, AlertSource

pytestmark = pytest.mark.contract

ALERTMANAGER: Mapping[str, Any] = {
    "receiver": "payments-team",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighErrorRate",
                "severity": "critical",
                "service": "checkout",
                "namespace": "production",
            },
            "annotations": {
                "summary": "checkout error rate above 5%",
                "description": "5xx responses are 12% of traffic over 5m",
            },
            "startsAt": "2026-08-05T12:04:11.000Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "https://prometheus.internal/graph?g0.expr=rate",
        }
    ],
    "groupLabels": {"alertname": "HighErrorRate"},
    "commonLabels": {"cluster": "eu-west-1"},
    "externalURL": "https://alertmanager.internal",
}

GRAFANA: Mapping[str, Any] = {
    "receiver": "payments-team",
    "status": "firing",
    "orgId": 1,
    "title": "[FIRING:1] CheckoutLatency (production)",
    "message": "p99 latency is 4.2s, threshold 1s",
    "state": "alerting",
    "ruleUrl": "https://grafana.internal/alerting/grafana/abc/view",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "CheckoutLatency",
                "severity": "warning",
                "service": "checkout",
            },
            "annotations": {"summary": "p99 latency above 1s"},
            "startsAt": "2026-08-05T12:06:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}

GRAFANA_LEGACY: Mapping[str, Any] = {
    "ruleName": "CheckoutLatency",
    "state": "alerting",
    "message": "p99 latency is 4.2s",
    "ruleUrl": "https://grafana.internal/d/abc",
    "evalMatches": [{"metric": "p99", "value": 4.2, "tags": {"service": "checkout"}}],
}

WEBHOOK: Mapping[str, Any] = {
    "title": "Checkout queue backing up",
    "severity": "warning",
    "service": "checkout",
    "description": "queue depth 12k and rising",
    "timestamp": "2026-08-05T12:07:00Z",
    "url": "https://internal.example/alerts/9",
}


def _raw(payload: Mapping[str, Any], **overrides: Any) -> RawAlert:
    return RawAlert(payload=payload, **overrides)


# -- detection ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (ALERTMANAGER, AlertSource.ALERTMANAGER),
        (GRAFANA, AlertSource.GRAFANA),
        (GRAFANA_LEGACY, AlertSource.GRAFANA),
        (WEBHOOK, AlertSource.WEBHOOK),
    ],
)
def test_each_payload_is_attributed_to_its_source(
    payload: Mapping[str, Any], expected: AlertSource
) -> None:
    assert normalise(_raw(payload)).alert_source is expected


def test_grafana_unified_alerting_is_not_mistaken_for_alertmanager() -> None:
    """Grafana's unified payload satisfies the Alertmanager shape on purpose, so
    the two are told apart by what Grafana adds rather than by adapter order."""
    assert normalise(_raw(GRAFANA)).alert_source is AlertSource.GRAFANA
    assert normalise(_raw(ALERTMANAGER)).alert_source is AlertSource.ALERTMANAGER


def test_prose_with_no_payload_is_plain_text() -> None:
    alert = normalise(RawAlert(text="hey, is checkout slow for anyone else?"))

    assert alert.alert_source is AlertSource.PLAIN_TEXT
    assert alert.summary == "hey, is checkout slow for anyone else?"


def test_the_transports_hint_beats_shape_detection() -> None:
    """The route a payload arrived on is a fact; its shape is an inference."""
    alert = normalise(_raw(WEBHOOK, source_hint="grafana"))

    assert alert.alert_source is AlertSource.GRAFANA


# -- extraction ---------------------------------------------------------------


def test_alertmanager_yields_the_fields_an_investigation_needs() -> None:
    alert = normalise(_raw(ALERTMANAGER))

    assert alert.alert_name == "HighErrorRate"
    assert alert.severity is Severity.CRITICAL
    assert alert.summary == "checkout error rate above 5%"
    assert alert.components == ("checkout", "production", "eu-west-1")
    assert alert.started_at == datetime(2026, 8, 5, 12, 4, 11, tzinfo=UTC)
    assert alert.reference.startswith("https://prometheus.internal")
    assert not alert.resolved


def test_alertmanagers_zero_end_time_means_the_alert_has_not_ended() -> None:
    """``0001-01-01T00:00:00Z`` parses cleanly and means "still firing"; taking
    it literally would produce a window that closed two thousand years ago."""
    assert normalise(_raw(ALERTMANAGER)).ended_at is None


def test_a_resolved_alertmanager_notification_is_marked_resolved() -> None:
    resolved = {
        **ALERTMANAGER,
        "status": "resolved",
        "alerts": [
            {**ALERTMANAGER["alerts"][0], "status": "resolved", "endsAt": "2026-08-05T12:30:00Z"}
        ],
    }

    alert = normalise(_raw(resolved))

    assert alert.resolved
    assert alert.ended_at == datetime(2026, 8, 5, 12, 30, tzinfo=UTC)


def test_grafana_unified_yields_its_rule_and_service() -> None:
    alert = normalise(_raw(GRAFANA))

    assert alert.alert_name == "CheckoutLatency"
    assert alert.severity is Severity.MEDIUM
    assert alert.components == ("checkout",)
    assert alert.reference.startswith("https://grafana.internal")


def test_grafana_legacy_reads_its_eval_matches() -> None:
    alert = normalise(_raw(GRAFANA_LEGACY))

    assert alert.alert_name == "CheckoutLatency"
    assert alert.components == ("checkout",)


def test_an_unrecognised_body_still_yields_its_conventional_fields() -> None:
    alert = normalise(_raw(WEBHOOK))

    assert alert.alert_name == "Checkout queue backing up"
    assert alert.severity is Severity.MEDIUM
    assert alert.components == ("checkout",)
    assert alert.started_at == datetime(2026, 8, 5, 12, 7, tzinfo=UTC)


# -- nothing raises -----------------------------------------------------------


@pytest.mark.parametrize("source", ALERT_SOURCES)
def test_an_empty_payload_normalises_rather_than_raising(source: AlertSource) -> None:
    """The alert that breaks intake is the one nobody looks at."""
    alert = normalise(RawAlert(payload={}, source_hint=source.value))

    assert isinstance(alert, NormalisedAlert)
    assert alert.alert_source is source


@pytest.mark.parametrize(
    "payload",
    [
        {"alerts": "not a list", "receiver": "x"},
        {"event": {"data": None}},
        {"alert_id": None, "tags": 17},
        {"alert": {"alertId": "x", "tags": {"not": "a list"}}},
        {"data": {"issue": []}},
        {"orgId": 1, "alerts": [None]},
    ],
)
def test_a_malformed_payload_normalises_rather_than_raising(
    payload: Mapping[str, Any],
) -> None:
    assert isinstance(normalise(_raw(payload)), NormalisedAlert)


def test_a_recognised_payload_with_no_headline_falls_back_to_the_raw_text() -> None:
    alert = normalise(
        RawAlert(payload={"unrecognised_field": "9"}, text="checkout is throwing 500s")
    )

    assert alert.alert_source is AlertSource.WEBHOOK
    assert alert.summary == "checkout is throwing 500s"
