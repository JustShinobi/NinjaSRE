"""The alert sources that have an adapter, and the two that catch everything else.

Closed, unlike the evidence-source vocabulary. An evidence source is whatever
system a capability read from and a vendor names its own; an alert source is a
payload shape somebody wrote a parser for, and a name with no parser behind it
would be a promise the normaliser cannot keep.

``WEBHOOK`` and ``PLAIN_TEXT`` are the two that always match. A JSON body
nobody recognises is still a JSON body with fields worth extracting, and a chat
message is still a sentence worth classifying — neither is an error.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class AlertSource(StrEnum):
    """Where an alert came from, as the pipeline records it."""

    ALERTMANAGER = "alertmanager"
    PAGERDUTY = "pagerduty"
    DATADOG = "datadog"
    GRAFANA = "grafana"
    SENTRY = "sentry"
    OPSGENIE = "opsgenie"
    WEBHOOK = "webhook"
    PLAIN_TEXT = "plain_text"

    @property
    def is_fallback(self) -> bool:
        """Return whether this source is one of the two that always match."""
        return self in _FALLBACK_SOURCES


_FALLBACK_SOURCES: Final[frozenset[AlertSource]] = frozenset(
    {AlertSource.WEBHOOK, AlertSource.PLAIN_TEXT}
)

#: Every source, for anything that has to enumerate them — a configuration
#: check, a console filter, the hint lookup in ``detect_source``. Which adapter
#: is *tried* first is the adapters' own order, in ``normalisation.py``, because
#: that is a property of the predicates rather than of the vocabulary.
ALERT_SOURCES: Final[tuple[AlertSource, ...]] = (
    AlertSource.ALERTMANAGER,
    AlertSource.GRAFANA,
    AlertSource.PAGERDUTY,
    AlertSource.DATADOG,
    AlertSource.SENTRY,
    AlertSource.OPSGENIE,
    AlertSource.WEBHOOK,
    AlertSource.PLAIN_TEXT,
)


__all__ = [
    "ALERT_SOURCES",
    "AlertSource",
]
