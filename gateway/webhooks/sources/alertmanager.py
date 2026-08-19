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

import yaml

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

#: What a copied receiver block says in place of a credential's value. Never a
#: template a caller could accidentally fill with one — this string is the
#: entire contents of that field, always, because ``receiver_yaml`` below has
#: no parameter a raw value could arrive through in the first place.
_CREDENTIALS_MARKER = 'paste the value of delivery token "{name}" here'


def receiver_yaml(*, url: str, token_name: str) -> str:
    """Return a ``webhook_configs`` block ready to paste into an Alertmanager receiver.

    Alertmanager's own YAML shape, generated rather than typed by an operator
    or assembled by concatenation on a screen — this is the one place that
    knows what an Alertmanager receiver actually looks like, which is why it
    lives beside the profile that already knows everything else about this
    vendor's webhook.

    Never carries a stored secret's value. A delivery token is never read back
    once it is issued — the store holds a hash, and this function has no
    parameter a value could arrive through even by mistake. What it carries
    instead is the token's own name, both in the marker where the value goes
    and readable beside it, so pasting this block and then finding the token by
    that name in Machine tokens is one lookup, not a guess.
    """
    block: dict[str, Any] = {
        "webhook_configs": [
            {
                "url": url,
                "http_config": {
                    "authorization": {
                        "type": "Bearer",
                        "credentials": _CREDENTIALS_MARKER.format(name=token_name),
                    }
                },
            }
        ]
    }
    return yaml.safe_dump(block, sort_keys=False)


__all__ = ["PROFILE", "receiver_yaml"]
