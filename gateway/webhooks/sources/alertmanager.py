"""Prometheus Alertmanager: shared-secret verification, and a *derived* delivery id.

``groupKey`` used to be the delivery identifier, and it is the wrong one:
Alertmanager sends the same group key for the firing notification, for every
re-notification, and for the resolution. Idempotency keyed on it answers the
resolution as "already processed", so the incident the firing opened never
closes — and 055 recorded exactly that, having had to vary ``groupKey`` in its
own tests to work around it.

The identifier here is the group key *plus what the notification says about the
group*: its status, and each alert's fingerprint with the instants it started
and ended. A byte-identical retry — a receiver that timed out and sent again —
derives the same identifier and is still one delivery. A notification saying
anything new about the group derives a different one and reaches the
deduplication step, which links it to the open investigation instead of
answering it as a duplicate.

An unchanged group re-notified after ``repeat_interval`` is genuinely
indistinguishable from a retry: Alertmanager sends no per-notification
identifier and no send timestamp. That is a property of the protocol rather
than a defect here, and it is why the *retry* window is minutes rather than the
hours a repeat interval runs to — see
``WEBHOOK_DELIVERY_RETRY_WINDOW_SECONDS``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field

#: How much of the digest rides in the identifier. Sixteen hex characters is
#: 64 bits, which makes a collision between two different notifications of one
#: group something that does not happen in a deployment's lifetime.
_DIGEST_CHARS = 16


def _members(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return what this notification says about each alert in the group.

    The vendor's own fingerprint where it sends one, and the labels' rendering
    where it does not — plus the two instants, because a group whose member
    resolved is a different notification from the one that opened it.
    """
    alerts = payload.get("alerts")
    if not isinstance(alerts, list):
        return ()
    return tuple(
        "|".join(
            (
                field(alert, "fingerprint") or repr(sorted((alert.get("labels") or {}).items())),
                field(alert, "status"),
                field(alert, "startsAt"),
                field(alert, "endsAt"),
            )
        )
        for alert in alerts
        if isinstance(alert, Mapping)
    )


def _event_id(payload: Mapping[str, Any]) -> str:
    """Return the identifier one Alertmanager *delivery* gets.

    Empty when the payload carries no group key, which is what
    ``IdempotencyIndex`` reads as "this source gives no stable identifier":
    no idempotency at all is the right answer there, rather than a false one
    keyed on nothing.
    """
    group_key = field(payload, "groupKey")
    if not group_key:
        return ""
    digest = hashlib.sha256(
        "\n".join((field(payload, "status"), *_members(payload))).encode("utf-8")
    ).hexdigest()[:_DIGEST_CHARS]
    return f"{group_key}@{digest}"


PROFILE = WebhookSourceProfile(
    source=AlertSource.ALERTMANAGER,
    event_id_of=_event_id,
    expects=(
        "Alertmanager's own grouped notification body: a `groupKey`, `commonLabels`, and an "
        "`alerts` array. Point a `webhook_config` at the URL; nothing else has to change."
    ),
    verification=(
        "a shared secret in the `Authorization` header, or a machine token scoped to alert delivery"
    ),
)

__all__ = ["PROFILE"]
