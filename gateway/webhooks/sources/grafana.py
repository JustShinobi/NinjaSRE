"""Grafana unified alerting: shared-secret verification, no stable event id.

Grafana's webhook body is deliberately Alertmanager-compatible; the two are
told apart by ``core.domain.alerts.normalisation``'s adapter matching, not by
which endpoint received the request.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.domain.alerts.sources import AlertSource
from gateway.webhooks.sources.profile import WebhookSourceProfile


def _event_id(_payload: Mapping[str, Any]) -> str:
    return ""


PROFILE = WebhookSourceProfile(
    source=AlertSource.GRAFANA,
    event_id_of=_event_id,
    expects=(
        "Grafana unified alerting's body: an `alerts` array with `labels` and `annotations`, plus the fields only Grafana sends. Configure it as a contact point of type webhook."
    ),
    verification=(
        "a shared secret in the `Authorization` header, or a machine token scoped to alert delivery"
    ),
)

__all__ = ["PROFILE"]
