"""Opsgenie: shared-secret verification, alert id for idempotency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "alert", "alertId") or field(payload, "alertId")


PROFILE = WebhookSourceProfile(
    source=AlertSource.OPSGENIE,
    event_id_of=_event_id,
    expects=(
        "an Opsgenie webhook body: an `action` and an `alert` object carrying `alertId` and `message`."
    ),
    verification=(
        "a shared secret in the `Authorization` header, or a machine token scoped to alert delivery"
    ),
)

__all__ = ["PROFILE"]
