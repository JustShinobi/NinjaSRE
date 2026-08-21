"""The shape every per-source module in this package exports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.alerts.sources import AlertSource


@dataclass(frozen=True, slots=True)
class WebhookSourceProfile:
    """What ``gateway/webhooks/router.py`` needs to know about one vendor's webhook."""

    source: AlertSource
    #: A stable per-delivery identifier, or the empty string when the vendor
    #: gives none. Normalisation itself is ``core.domain.alerts.normalisation``'s
    #: job, reached through ``adapter_for(profile.source)``.
    event_id_of: Callable[[Mapping[str, Any]], str]


def field(payload: Mapping[str, Any], *path: str) -> str:
    """Return the string at a dotted ``path`` inside ``payload``, or the empty string."""
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(key)
    return str(current) if current is not None else ""


__all__ = ["WebhookSourceProfile", "field"]
