"""PagerDuty: HMAC signature verification (``X-PagerDuty-Signature``), event id for idempotency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "event", "id") or field(payload, "id")


PROFILE = WebhookSourceProfile(
    source=AlertSource.PAGERDUTY,
    event_id_of=_event_id,
    expects=("a PagerDuty v3 webhook body: an `event` object with an `id` and an `event_type`."),
    verification=(
        "PagerDuty's HMAC signature in `X-PagerDuty-Signature`, or a machine token scoped to alert delivery"
    ),
)

__all__ = ["PROFILE"]
