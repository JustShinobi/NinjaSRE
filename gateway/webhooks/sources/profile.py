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
    #: What the sender must post, in one sentence an operator reads while
    #: configuring the other end. Beside the profile rather than in the console,
    #: because the shape the adapter parses and the shape the console claims it
    #: parses have to be one fact — and the day they are two, the console is the
    #: one that is wrong.
    expects: str = ""
    #: How a delivery from this source is trusted. The vendor's own mechanism
    #: where it has one; every source additionally accepts a machine token
    #: scoped to alert delivery, which is what a sender with no signing scheme
    #: uses.
    verification: str = ""


def field(payload: Mapping[str, Any], *path: str) -> str:
    """Return the string at a dotted ``path`` inside ``payload``, or the empty string."""
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(key)
    return str(current) if current is not None else ""


__all__ = ["WebhookSourceProfile", "field"]
