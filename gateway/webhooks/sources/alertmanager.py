"""Prometheus Alertmanager: shared-secret verification, ``groupKey`` for idempotency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "groupKey")


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
