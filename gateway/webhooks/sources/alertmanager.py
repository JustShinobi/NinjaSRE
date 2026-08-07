"""Prometheus Alertmanager: shared-secret verification, ``groupKey`` for idempotency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "groupKey")


PROFILE = WebhookSourceProfile(source=AlertSource.ALERTMANAGER, event_id_of=_event_id)

__all__ = ["PROFILE"]
