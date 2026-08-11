"""The transit surface: is this source alive, what would this rule do, where did it go.

The acceptance criteria this feature is judged on, against the routes the
screen actually calls. The one that matters most is the cheapest to state: a
source that has never delivered appears in the listing, flagged, without the
operator having to look for it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from config.constants.transit import (
    DELIVERY_DETAIL_FULL_REPORT,
    DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
    NO_DELIVERY_CHANNEL_REASON,
)
from platform.config_service.service import ConfigService
from platform.identity.permissions import Role
from platform.persistence.ports import (
    PayloadSample,
    TenantScope,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


async def admin(deployment: Deployment) -> dict[str, str]:
    """Return the header of a principal that may read and write configuration."""
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.ADMIN,
        node_id=TEAM_PAYMENTS,
    )
    return {"Authorization": f"Bearer {secret}"}


async def settings(deployment: Deployment, patch: dict[str, Any]) -> None:
    """Store ``patch`` on the team node the token below is scoped to."""
    service = ConfigService(gateway=deployment.gateway, scope=TenantScope(org_id=ORG))
    await service.set_settings(TEAM_PAYMENTS, patch, actor_id="ada")


async def ledger(deployment: Deployment, delivery: TransitDelivery) -> None:
    """Write one row straight into the ledger."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.transit.record(delivery)


def arrival(**overrides: Any) -> TransitDelivery:
    """Return one ingress crossing."""
    return TransitDelivery(
        **{
            "delivery_id": "alertmanager-1",
            "direction": TransitDirection.INGRESS,
            "source": "alertmanager",
            "occurred_at": datetime.now(UTC),
            "outcome": TransitOutcome.ACCEPTED,
            **overrides,
        }
    )


# --- Ingress status: acceptance 1 and 2 -------------------------------------------


async def test_every_configured_receiver_appears_whether_or_not_it_ever_delivered(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 2. Built by enumerating the receivers, never from the ledger."""
    response = await client.get("/v1/transit/ingress", headers=await admin(deployment))

    assert response.status_code == 200, response.text
    sources = {row["source"]: row for row in response.json()["sources"]}
    assert len(sources) == 7
    assert all(row["never_delivered"] for row in sources.values())


async def test_a_source_that_delivered_stops_being_flagged(
    client: AsyncClient, deployment: Deployment
) -> None:
    await ledger(deployment, arrival())

    response = await client.get("/v1/transit/ingress", headers=await admin(deployment))

    rows = {row["source"]: row for row in response.json()["sources"]}
    assert rows["alertmanager"]["never_delivered"] is False
    assert rows["alertmanager"]["last_outcome"] == "accepted"
    assert rows["grafana"]["never_delivered"] is True


async def test_a_row_names_the_url_the_format_and_the_last_delivery(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 1: URL, expected format, and the last delivery with its outcome."""
    await ledger(deployment, arrival())

    response = await client.get("/v1/transit/ingress", headers=await admin(deployment))

    row = next(r for r in response.json()["sources"] if r["source"] == "alertmanager")
    assert row["path"] == "/webhooks/alertmanager"
    assert "groupKey" in row["expects"]
    assert row["verification"]
    assert row["last_delivery_at"]


async def test_the_masked_sample_rides_on_the_row(
    client: AsyncClient, deployment: Deployment
) -> None:
    await ledger(deployment, arrival())
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=AT,
                body='{"status":"firing"}',
                masking_policy="standard",
            )
        )

    response = await client.get("/v1/transit/ingress", headers=await admin(deployment))

    row = next(r for r in response.json()["sources"] if r["source"] == "alertmanager")
    assert row["sample"]["body"] == '{"status":"firing"}'
    assert row["sample"]["masking_policy"] == "standard"


async def test_recent_rejections_come_back_with_their_reasons(
    client: AsyncClient, deployment: Deployment
) -> None:
    await ledger(deployment, arrival())
    await ledger(
        deployment,
        arrival(
            delivery_id="refused-1",
            outcome=TransitOutcome.REJECTED,
            reason="did not verify against any configured route",
        ),
    )

    response = await client.get("/v1/transit/ingress", headers=await admin(deployment))

    row = next(r for r in response.json()["sources"] if r["source"] == "alertmanager")
    assert [entry["reason"] for entry in row["recent_rejections"]] == [
        "did not verify against any configured route"
    ]


# --- Rules and simulation: acceptance 3 and 4 -------------------------------------


async def test_the_catch_all_is_always_in_the_rule_listing(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 4: the fate of an unmatched delivery is always visible."""
    response = await client.get("/v1/transit/rules", headers=await admin(deployment))

    rules = response.json()["rules"]
    assert rules[-1]["is_catch_all"] is True
    assert rules[-1]["action"] == "investigate"


async def test_a_configured_rule_set_keeps_its_order_and_its_last_word(
    client: AsyncClient, deployment: Deployment
) -> None:
    await settings(
        deployment,
        {
            "transit": {
                "rules": [
                    {
                        "rule_id": "noisy",
                        "sources": ["sentry"],
                        "action": "discard",
                        "reason": "chatter",
                    },
                    {"rule_id": "rest", "action": "investigate"},
                ]
            }
        },
    )

    response = await client.get("/v1/transit/rules", headers=await admin(deployment))

    rules = response.json()["rules"]
    assert [rule["rule_id"] for rule in rules] == ["noisy", "rest"]
    assert rules[0]["is_catch_all"] is False
    assert rules[-1]["is_catch_all"] is True


async def test_a_pasted_payload_is_simulated_against_the_rules_before_anything_is_saved(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 3: rule, team, and action, from a real payload."""
    await settings(
        deployment,
        {
            "transit": {
                "rules": [
                    {
                        "rule_id": "quiet-alertmanager",
                        "sources": ["alertmanager"],
                        "action": "discard",
                        "reason": "being decommissioned",
                    },
                    {"rule_id": "rest", "action": "investigate"},
                ]
            }
        },
    )

    response = await client.post(
        "/v1/transit/simulate",
        headers=await admin(deployment),
        json={
            "source": "alertmanager",
            "payload": {"groupKey": "g", "status": "firing", "alerts": []},
        },
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["rule_id"] == "quiet-alertmanager"
    assert answer["action"] == "discard"
    assert answer["reason"] == "being decommissioned"
    assert answer["team"] == TEAM_PAYMENTS


async def test_a_delivery_already_in_the_ledger_can_be_simulated_by_its_id(
    client: AsyncClient, deployment: Deployment
) -> None:
    await ledger(deployment, arrival(delivery_id="pick-me"))

    response = await client.post(
        "/v1/transit/simulate",
        headers=await admin(deployment),
        json={"delivery_id": "pick-me"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["rule_id"] == "catch-all"


async def test_simulating_a_delivery_nobody_has_is_a_404(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.post(
        "/v1/transit/simulate",
        headers=await admin(deployment),
        json={"delivery_id": "never-happened"},
    )

    assert response.status_code == 404


async def test_simulating_against_a_receiver_this_deployment_does_not_serve_is_refused(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.post(
        "/v1/transit/simulate",
        headers=await admin(deployment),
        json={"source": "nagios", "payload": {}},
    )

    assert response.status_code == 400


async def test_a_simulation_stores_nothing(client: AsyncClient, deployment: Deployment) -> None:
    """The 058 discipline: nothing that decides behaviour is saved by looking at it."""
    await client.post(
        "/v1/transit/simulate",
        headers=await admin(deployment),
        json={"source": "generic", "payload": {"alert_name": "X"}},
    )

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        from platform.persistence.ports import TransitQuery

        assert await uow.transit.deliveries(TransitQuery()) == ()


# --- Destinations: acceptance 5 and the known gap ---------------------------------


async def test_a_destination_declares_its_events_channel_detail_and_masking_policy(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 5, whole."""
    await settings(
        deployment,
        {
            "surfaces": {"channels": [{"platform": "slack", "channel": "#incidents"}]},
            "transit": {
                "destinations": [
                    {
                        "destination_id": "ops",
                        "channel": "slack",
                        "events": [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
                        "detail": DELIVERY_DETAIL_FULL_REPORT,
                    }
                ]
            },
        },
    )

    response = await client.get("/v1/transit/destinations", headers=await admin(deployment))

    row = response.json()["destinations"][0]
    assert row["channel"] == "slack"
    assert row["events"] == [DELIVERY_EVENT_INVESTIGATION_CONCLUDED]
    assert row["detail"] == DELIVERY_DETAIL_FULL_REPORT
    assert row["masking_policy"] == "standard"
    assert row["unconfigurable_reason"] == ""


async def test_a_deployment_with_no_channel_says_why_destinations_cannot_be_configured(
    client: AsyncClient, deployment: Deployment
) -> None:
    """T-010, and the 054 known-gap posture rather than a screen that looks finished."""
    response = await client.get("/v1/transit/destinations", headers=await admin(deployment))

    assert response.json()["unconfigurable_reason"] == NO_DELIVERY_CHANNEL_REASON


async def test_a_destination_bound_to_a_channel_nobody_wired_says_so(
    client: AsyncClient, deployment: Deployment
) -> None:
    await settings(
        deployment,
        {
            "surfaces": {"channels": [{"platform": "slack", "channel": "#incidents"}]},
            "transit": {
                "destinations": [
                    {
                        "destination_id": "ops",
                        "channel": "discord",
                        "events": [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
                    }
                ]
            },
        },
    )

    response = await client.get("/v1/transit/destinations", headers=await admin(deployment))

    assert "discord" in response.json()["destinations"][0]["unconfigurable_reason"]


# --- Re-sending a failed delivery: acceptance 6 -----------------------------------


async def test_a_failed_delivery_can_be_sent_again_and_the_ask_is_audited(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 6. A re-send puts a report in front of somebody: it is a human act."""
    await ledger(
        deployment,
        TransitDelivery(
            delivery_id="ops:concluded:1",
            direction=TransitDirection.OUTBOUND,
            source="ops",
            occurred_at=AT,
            outcome=TransitOutcome.FAILED,
            reason="the channel refused the message",
            event_type=DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
            detail={"channel": "slack"},
        ),
    )

    response = await client.post(
        "/v1/transit/deliveries/ops:concluded:1/resend", headers=await admin(deployment)
    )

    assert response.status_code == 200, response.text
    assert response.json()["attempt"] == 2

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query(action="delivery.resend")
    assert [event.resource_id for event in events] == ["ops:concluded:1"]


async def test_a_delivery_that_did_not_fail_is_not_re_sendable(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Re-sending a message the destination accepted would produce a duplicate."""
    await ledger(
        deployment,
        TransitDelivery(
            delivery_id="ops:concluded:2",
            direction=TransitDirection.OUTBOUND,
            source="ops",
            occurred_at=AT,
            outcome=TransitOutcome.DELIVERED,
            event_type=DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
        ),
    )

    response = await client.post(
        "/v1/transit/deliveries/ops:concluded:2/resend", headers=await admin(deployment)
    )

    assert response.status_code == 400


async def test_an_ingress_row_cannot_be_re_sent(
    client: AsyncClient, deployment: Deployment
) -> None:
    """There is nothing to send: an arrival is something that happened to us."""
    await ledger(deployment, arrival(outcome=TransitOutcome.REJECTED, reason="unverified"))

    response = await client.post(
        "/v1/transit/deliveries/alertmanager-1/resend", headers=await admin(deployment)
    )

    assert response.status_code == 404


# --- Permissions -------------------------------------------------------------------


async def test_a_viewer_cannot_re_send_a_delivery(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="vic",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )

    response = await client.post(
        "/v1/transit/deliveries/anything/resend",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 403
