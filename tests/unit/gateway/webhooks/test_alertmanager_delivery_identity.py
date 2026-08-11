"""What counts as *the same delivery* from Alertmanager, and what does not.

055 left this open, and named the cost: with ``groupKey`` as the delivery
identifier, everything Alertmanager says about one group is one delivery, so a
resolution is answered "already processed" and the incident the firing opened
never closes. Its own tests had to vary ``groupKey`` — something a real
Alertmanager never does — to get around it.

Two changes close it, and they are one idea from two sides. The identifier is
now derived from what the notification *says* about the group, so a
notification carrying anything new is a new delivery. And the window a delivery
is remembered in is the length of an HTTP retry rather than the length of the
deduplication window, so a later notification of an unchanged group falls out of
idempotency while still inside deduplication — and is linked to the open
investigation instead of being answered as a duplicate and forgotten.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient

from gateway.http.state import GatewayState
from gateway.webhooks.sources.alertmanager import PROFILE
from tests.unit.gateway.webhooks.test_router import (
    alertmanager_payload,
    valid_headers,
    webhook_app,  # noqa: F401 — the fixture this module runs against
)

pytestmark = pytest.mark.asyncio


def resolved(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``payload`` as Alertmanager sends it once the group goes green.

    Same ``groupKey`` — which is exactly the point. A real Alertmanager does not
    mint a new one for the resolution.
    """
    alerts = [
        {**alert, "status": "resolved", "endsAt": "2026-08-06T12:30:00Z"}
        for alert in payload["alerts"]
    ]
    return {**payload, "status": "resolved", "alerts": alerts}


async def deliver(client: AsyncClient, payload: dict[str, Any]) -> Any:
    """Post one genuine Alertmanager delivery."""
    body = json.dumps(payload).encode("utf-8")
    return await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )


# --- The identifier itself --------------------------------------------------------


def test_the_same_notification_twice_is_the_same_delivery() -> None:
    """A receiver that timed out and sent the same body again sent one delivery."""
    payload = alertmanager_payload()

    assert PROFILE.event_id_of(payload) == PROFILE.event_id_of(alertmanager_payload())


def test_a_resolution_is_not_the_same_delivery_as_its_firing() -> None:
    """The defect 055 recorded, stated as an assertion."""
    firing = alertmanager_payload()

    assert PROFILE.event_id_of(resolved(firing)) != PROFILE.event_id_of(firing)


def test_a_group_that_gained_a_member_is_not_the_same_delivery() -> None:
    firing = alertmanager_payload()
    joined = {**firing, "alerts": [*firing["alerts"], {**firing["alerts"][0], "startsAt": "later"}]}

    assert PROFILE.event_id_of(joined) != PROFILE.event_id_of(firing)


def test_a_payload_with_no_group_key_gets_no_identifier() -> None:
    """No idempotency at all, rather than a false one keyed on nothing."""
    assert PROFILE.event_id_of({"status": "firing", "alerts": []}) == ""


def test_the_group_key_is_still_readable_in_the_identifier() -> None:
    """So a log line and a ledger row can still be traced back to the group."""
    assert PROFILE.event_id_of(alertmanager_payload()).startswith("group-1@")


# --- What it buys on the live path ------------------------------------------------


async def test_a_resolution_of_the_group_the_firing_opened_closes_its_incident(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """The whole of the handoff, against a payload shaped the way the vendor sends it.

    Before this, the second delivery answered ``duplicate_delivery`` and the
    incident stayed open with an upstream that had gone green.
    """
    client, _state = webhook_app
    firing = alertmanager_payload()

    opened = await deliver(client, firing)
    closing = await deliver(client, resolved(firing))

    assert opened.json()["incident_id"]
    assert closing.json().get("duplicate_delivery") is None
    assert closing.json()["resolution"] == "linked"
    assert closing.json()["incident_id"] == opened.json()["incident_id"]


async def test_a_re_notification_outside_the_retry_window_links_rather_than_repeats(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """An unchanged group re-notified later is the investigation it already has.

    Alertmanager sends nothing that distinguishes a re-notification of an
    unchanged group from an HTTP retry of one, so the *window* is what
    separates them: past the retry window and inside the deduplication one,
    this is a delivery to link rather than one to drop.
    """
    client, state = webhook_app
    firing = alertmanager_payload()

    # The clock the idempotency index reads, driven rather than waited for: a
    # test that slept sixty seconds would be a test nobody runs, and one that
    # read the wall clock would be a test that passes or fails by luck. The
    # deduplication index keeps its own real clock, so its ten-minute window is
    # still open when this one's minute has passed — which is the difference
    # between the two windows, exercised.
    elapsed = [0.0]
    state.webhook_idempotency.clock = lambda: elapsed[0]

    first = await deliver(client, firing)
    elapsed[0] = state.webhook_idempotency.window_seconds + 1.0
    second = await deliver(client, firing)

    assert second.json().get("duplicate_delivery") is None
    assert second.json()["linked"] is True
    assert second.json()["run_id"] == first.json()["run_id"]
