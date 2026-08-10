"""The generic signed webhook: HMAC verification, an operator-defined event id field."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "event_id") or field(payload, "id")


PROFILE = WebhookSourceProfile(
    source=AlertSource.WEBHOOK,
    event_id_of=_event_id,
    expects=(
        "any JSON object naming the alert: `alert_name`, `summary`, `severity`, and an `event_id` or `id` if the sender has one. What anything without a vendor integration posts."
    ),
    verification=(
        "an HMAC-SHA256 signature over the body in `X-Webhook-Signature`, or a machine token scoped to alert delivery"
    ),
)

__all__ = ["PROFILE"]
