"""Every path through the webhook handler leaves a row, including the refusals.

A rejected delivery that leaves no trace is the silent failure this feature
exists to kill, so "record it if it worked" is exactly the wrong shape. The
assertions below walk the seven ways a delivery can end and check that each one
is a row an operator can read, with the reason on it.

The masking half is the other property: the sample stored for a source has been
through the deployment's masking policy, and a sentinel address in the raw body
is not in the stored sample.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES
from gateway.http.state import GatewayState
from platform.persistence.ports import (
    TenantScope,
    TransitDelivery,
    TransitOutcome,
    TransitQuery,
)
from tests.unit.gateway.http.conftest import ORG
from tests.unit.gateway.webhooks.test_router import (
    SECRET,
    alertmanager_payload,
    valid_headers,
    webhook_app,  # noqa: F401 — the fixture this module runs against
)

pytestmark = pytest.mark.asyncio

#: An address in the documentation range, put in the payload so the assertion
#: about masking is about a value nothing else in the fixture could produce.
SENTINEL_ADDRESS = "203.0.113.77"


async def rows(state: GatewayState) -> tuple[TransitDelivery, ...]:
    """Return every ledger row this deployment has written."""
    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.transit.deliveries(TransitQuery())


async def only_row(state: GatewayState) -> TransitDelivery:
    """Return the single ledger row, asserting there is exactly one."""
    written = await rows(state)
    assert len(written) == 1, written
    return written[0]


async def deliver(client: AsyncClient, payload: dict[str, object] | None = None) -> None:
    """Post one genuine Alertmanager delivery."""
    body = json.dumps(payload if payload is not None else alertmanager_payload()).encode("utf-8")
    await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )


# --- A row on every path ----------------------------------------------------------


async def test_an_accepted_delivery_is_a_row(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app

    await deliver(client)

    row = await only_row(state)
    assert row.outcome is TransitOutcome.ACCEPTED
    assert row.source == "alertmanager"
    assert row.run_id
    assert row.incident_id


async def test_an_unverified_delivery_is_a_row_with_its_reason(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """The most important one. Today this is a 401 and a log line nobody reads."""
    client, state = webhook_app
    body = json.dumps(alertmanager_payload()).encode("utf-8")

    response = await client.post(
        "/webhooks/alertmanager",
        content=body,
        headers={"Authorization": "Bearer not-the-real-secret"},
    )

    assert response.status_code == 401
    row = await only_row(state)
    assert row.outcome is TransitOutcome.REJECTED
    assert "did not verify" in row.reason


async def test_an_oversize_delivery_is_a_row_with_its_reason(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app

    response = await client.post(
        "/webhooks/alertmanager",
        content=b"x" * (WEBHOOK_MAX_PAYLOAD_BYTES + 1),
        headers={"Authorization": f"Bearer {SECRET}"},
    )

    assert response.status_code == 413
    row = await only_row(state)
    assert row.outcome is TransitOutcome.REJECTED
    assert "exceeds" in row.reason


async def test_an_unparseable_delivery_is_a_row_with_its_reason(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app
    body = b"{not json at all"

    response = await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )

    assert response.status_code == 400
    row = await only_row(state)
    assert row.outcome is TransitOutcome.REJECTED
    assert "not valid JSON" in row.reason


async def test_a_repeated_delivery_is_a_row_of_its_own(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """Two arrivals of one event are two ledger rows and one investigation.

    The ledger identifies an arrival; the idempotency index identifies an
    event. Collapsing the two would make "it was delivered twice" unanswerable.
    """
    client, state = webhook_app
    payload = alertmanager_payload()

    await deliver(client, payload)
    await deliver(client, payload)

    written = await rows(state)
    assert [row.outcome for row in written] == [
        TransitOutcome.DUPLICATE,
        TransitOutcome.ACCEPTED,
    ]


async def test_a_shed_storm_is_one_row_carrying_how_many_were_dropped(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """A storm is one fact. A row per refused request would be the unbounded
    growth the shedder exists to prevent, paid in the store instead."""
    client, state = webhook_app
    state.webhook_shedder.max_requests = 1

    for index in range(3):
        await deliver(client, {**alertmanager_payload(), "groupKey": f"storm-{index}"})

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        shed = await uow.transit.deliveries(TransitQuery(outcomes=(TransitOutcome.SHED,)))

    assert len(shed) == 1
    assert shed[0].detail["shed_in_window"] == "1"
    assert "above the limit" in shed[0].reason


# --- The masked sample ------------------------------------------------------------


async def test_the_stored_sample_has_been_through_the_masking_policy(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """T-002: a sentinel in the raw payload is absent from the stored sample."""
    client, state = webhook_app
    payload = alertmanager_payload()
    payload["commonLabels"] = {"alertname": "HighErrorRate", "instance": SENTINEL_ADDRESS}

    await deliver(client, payload)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        sample = await uow.transit.sample("alertmanager")

    assert sample is not None
    assert SENTINEL_ADDRESS not in sample.body
    assert "HighErrorRate" in sample.body


async def test_the_sample_names_the_policy_that_produced_it(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """A sample captured under one policy, shown beside the name of another,
    would be a lie about what was withheld."""
    client, state = webhook_app

    await deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        sample = await uow.transit.sample("alertmanager")

    assert sample is not None
    assert sample.masking_policy == "standard"


async def test_one_source_keeps_one_sample_and_it_is_the_last(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app

    await deliver(client, {**alertmanager_payload(), "groupKey": "first"})
    await deliver(client, {**alertmanager_payload(), "groupKey": "second"})

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        sample = await uow.transit.sample("alertmanager")

    assert sample is not None
    assert '"second"' in sample.body


async def test_an_unverified_sender_leaves_no_sample(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """Keeping one would let anybody who can reach the URL put text of their
    choosing into a store an operator later reads."""
    client, state = webhook_app
    body = json.dumps({"forged": SENTINEL_ADDRESS}).encode("utf-8")

    await client.post(
        "/webhooks/alertmanager",
        content=body,
        headers={"Authorization": "Bearer not-the-real-secret"},
    )

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        assert await uow.transit.sample("alertmanager") is None


async def test_a_body_that_would_not_parse_is_sampled_anyway(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """ "Did the format change" is exactly the question a parse failure raises."""
    client, state = webhook_app
    body = b"<html>not what we asked for</html>"

    await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        sample = await uow.transit.sample("alertmanager")

    assert sample is not None
    assert "not what we asked for" in sample.body
