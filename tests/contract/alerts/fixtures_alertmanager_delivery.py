"""The grouped notification body Alertmanager posts, exactly as the stack sends it.

Not this repository's own idea of a webhook payload: Alertmanager's own v4
grouped shape — ``groupKey``, ``commonLabels``, and an ``alerts`` array, each
alert carrying the vendor's own fingerprint, start and end instants. The intake
route has to accept this body without a format of its own, and these constants
are what a contract test holds it against.

Three deliveries, one group. ``ALERTMANAGER_FIRING_GROUPED`` is the notification
a real rule sends first: two members firing together in one group, because a
route that only ever sees one alert per delivery never proves grouping is
handled at all. ``ALERTMANAGER_FIRING_GROUPED_RETRY`` is a genuinely separate
object holding the same values — Alertmanager's own retry, or the same group
re-notified inside the retry window before its repeat interval elapses — built
by copy rather than restated by hand, so a duplicate-detection test is proved
against two objects rather than one literal that happens to equal itself.
``ALERTMANAGER_RESOLVED_SAME_GROUP`` is what the same group sends once every
member clears: the same ``groupKey`` and the same per-alert fingerprints (a
fingerprint identifies an alert by its labels, not by which notification
mentions it), a different status, and a real ``endsAt`` in place of
Alertmanager's own zero-value one.

The rule is ``InstanceDown``, one of the rules already active and firing on
its own ahead of this feature. The service names are pseudonyms, in the same
spirit the rest of this repository's fixture data keeps: what proves the
intake route works is the shape of a real delivery, not which container it
happened to name.

No secret rides in any of these. The credential that authenticates a delivery
is a bearer token in the ``Authorization`` header, not a field of the body, and
none of the three constants below carries a header at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

#: The rule this fixture exercises. One of the rules already active on the
#: cluster this feature targets, rather than invented: a route that only ever
#: worked against a name nothing fires would prove nothing about the
#: deployment it is built for.
_ALERT_NAME = "InstanceDown"

#: Alertmanager's own zero-value ``endsAt`` for an alert that has not ended.
#: Parsing it as a real timestamp would read a firing alert as one that ended
#: two thousand years ago, so every consumer of this fixture has to treat it as
#: "not ended" rather than as a date.
_NOT_ENDED = "0001-01-01T00:00:00Z"

#: The group key Alertmanager derives for a route grouped only by
#: ``alertname``, with no other label in ``group_by``. Shared across all three
#: constants below: a retry or a resolution that changed the group key would
#: not be describing the same group any more.
_GROUP_KEY = '{}:{alertname="InstanceDown"}'

ALERTMANAGER_FIRING_GROUPED: Mapping[str, Any] = {
    "version": "4",
    "groupKey": _GROUP_KEY,
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "ninjasre-alert-intake",
    "groupLabels": {"alertname": _ALERT_NAME},
    "commonLabels": {
        "alertname": _ALERT_NAME,
        "severity": "critical",
        "job": "blackbox-http",
    },
    "commonAnnotations": {},
    "externalURL": "http://alertmanager.cluster.internal:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": _ALERT_NAME,
                "job": "blackbox-http",
                "instance": "cedar.cluster.internal:1935",
                "service": "cedar",
                "node": "node01",
                "zone": "apps",
                "severity": "critical",
            },
            "annotations": {
                "summary": "cedar is down",
                "description": "the blackbox probe against cedar has failed for more than 1m",
            },
            "startsAt": "2026-08-19T14:32:00Z",
            "endsAt": _NOT_ENDED,
            "generatorURL": ("http://prometheus.cluster.internal:9090/graph?g0.expr=probe_success"),
            "fingerprint": "8f3a1c2d9e4b5f60",
        },
        {
            "status": "firing",
            "labels": {
                "alertname": _ALERT_NAME,
                "job": "blackbox-http",
                "instance": "birch.cluster.internal:6767",
                "service": "birch",
                "node": "node02",
                "zone": "apps",
                "severity": "critical",
            },
            "annotations": {
                "summary": "birch is down",
                "description": "the blackbox probe against birch has failed for more than 1m",
            },
            "startsAt": "2026-08-19T14:32:05Z",
            "endsAt": _NOT_ENDED,
            "generatorURL": ("http://prometheus.cluster.internal:9090/graph?g0.expr=probe_success"),
            "fingerprint": "2b7d4e8a1f0c3956",
        },
    ],
}

#: A genuinely separate object holding the same values as
#: ``ALERTMANAGER_FIRING_GROUPED``. Built by copy rather than restated by hand,
#: so it cannot drift from the notification it is a redelivery of — which is
#: the one property a duplicate-detection test needs from it.
ALERTMANAGER_FIRING_GROUPED_RETRY: Mapping[str, Any] = deepcopy(ALERTMANAGER_FIRING_GROUPED)

ALERTMANAGER_RESOLVED_SAME_GROUP: Mapping[str, Any] = {
    "version": "4",
    "groupKey": _GROUP_KEY,
    "truncatedAlerts": 0,
    "status": "resolved",
    "receiver": "ninjasre-alert-intake",
    "groupLabels": {"alertname": _ALERT_NAME},
    "commonLabels": {
        "alertname": _ALERT_NAME,
        "severity": "critical",
        "job": "blackbox-http",
    },
    "commonAnnotations": {},
    "externalURL": "http://alertmanager.cluster.internal:9093",
    "alerts": [
        {
            "status": "resolved",
            "labels": dict(ALERTMANAGER_FIRING_GROUPED["alerts"][0]["labels"]),
            "annotations": {
                "summary": "cedar is down",
                "description": "the blackbox probe against cedar has failed for more than 1m",
            },
            "startsAt": "2026-08-19T14:32:00Z",
            "endsAt": "2026-08-19T14:41:00Z",
            "generatorURL": ("http://prometheus.cluster.internal:9090/graph?g0.expr=probe_success"),
            # Stable across firing and resolved: the fingerprint identifies the
            # alert by its labels, not by whichever notification mentions it.
            "fingerprint": "8f3a1c2d9e4b5f60",
        },
        {
            "status": "resolved",
            "labels": dict(ALERTMANAGER_FIRING_GROUPED["alerts"][1]["labels"]),
            "annotations": {
                "summary": "birch is down",
                "description": "the blackbox probe against birch has failed for more than 1m",
            },
            "startsAt": "2026-08-19T14:32:05Z",
            "endsAt": "2026-08-19T14:41:05Z",
            "generatorURL": ("http://prometheus.cluster.internal:9090/graph?g0.expr=probe_success"),
            "fingerprint": "2b7d4e8a1f0c3956",
        },
    ],
}

__all__ = [
    "ALERTMANAGER_FIRING_GROUPED",
    "ALERTMANAGER_FIRING_GROUPED_RETRY",
    "ALERTMANAGER_RESOLVED_SAME_GROUP",
]
