"""Datadog: shared-secret verification (a custom header token), no stable event id."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile, field


def _event_id(payload: Mapping[str, Any]) -> str:
    return field(payload, "id")


PROFILE = WebhookSourceProfile(source=AlertSource.DATADOG, event_id_of=_event_id)

__all__ = ["PROFILE"]
