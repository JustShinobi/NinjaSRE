"""A derived identifier has to fit the column it is stored in.

``timeline_key`` composes an incident id with a free-text detail — a resource
identifier, "3 subject(s)", whatever the caller had to say — and the result is
the primary key of a ``varchar`` column. An incident correlated on a full
digest, opened at an instant with microseconds, and described in a short
sentence composes past that width, and the write fails with a database error
that reads like an outage.

Nothing caught it because the in-memory store has no column widths, and the
suite that runs against a real PostgreSQL is not part of the ordinary gate. It
surfaced the first time a real alert was delivered to a real deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.persistence import MAX_IDENTIFIER_CHARS
from platform.persistence.ports.incident_store import TimelineKind, timeline_key

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 22, 11, 26, 43, 966904, tzinfo=UTC)

#: What an Alertmanager delivery actually produces: an incident correlated on a
#: sha256 the deployment derived, opened at a microsecond instant.
LONG_INCIDENT = (
    "alert:alertmanager:"
    "bf26ea4bae2a1c8fd25825a2e21da4cb5e1e98379631ef4e99b9b2e374d36b57"
    "@2026-08-22T11:26:43.966904+00:00"
)


def test_a_key_composed_from_a_real_delivery_fits_the_column() -> None:
    key = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.OPENED, AT)

    assert len(key) <= MAX_IDENTIFIER_CHARS


def test_a_short_key_is_left_legible() -> None:
    """Shortening every key would make a readable one unreadable for nothing."""
    key = timeline_key("alert:acme:1", TimelineKind.OPENED, AT)

    assert key == f"alert:acme:1@opened@{AT.isoformat()}"


def test_two_different_keys_stay_different_after_shortening() -> None:
    first = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.OPENED, AT)
    second = timeline_key(f"{LONG_INCIDENT}:4 subject(s)", TimelineKind.OPENED, AT)

    assert first != second


def test_the_same_key_is_derived_twice() -> None:
    """Determinism is the whole reason this is derived rather than generated."""
    first = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.OPENED, AT)
    second = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.OPENED, AT)

    assert first == second


def test_the_kind_still_separates_two_entries_at_one_instant() -> None:
    opened = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.OPENED, AT)
    correlated = timeline_key(f"{LONG_INCIDENT}:3 subject(s)", TimelineKind.CORRELATED, AT)

    assert opened != correlated
