"""The autonomy routes: what they return, what they refuse, and who may reach them.

Driven over the real application with a real issued token, so the permission
table, the tenancy check and the configuration service are all the ones a
deployment runs. The interesting half is the refusals: a malformed policy is
rejected before storage with the field named, and a viewer can read the posture
and cannot change it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.asyncio

POLICY = f"/v1/autonomy/policy/{TEAM_PAYMENTS}"


def a_rule(level: str, **scope: Any) -> dict[str, Any]:
    """Return one rule in the document's shape."""
    return {"scope": {"kind": scope.pop("kind", "deployment"), **scope}, "level": level}


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, GatewayState, str]]:
    """Yield a client, the state behind it, and an owner's bearer token."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )

    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=FakeInvestigationRunner()
    )
    secret = await issue_token(
        store, state.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield client, state, secret


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def test_an_unconfigured_node_reports_the_empty_posture(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    response = await client.get(POLICY, headers=bearer(secret))
    assert response.status_code == 200
    body = response.json()
    assert body["rules"] == []
    assert body["dry_run"] is False


async def test_a_written_policy_reads_back_as_the_same_document(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    document = {
        "dry_run": False,
        "rules": [
            a_rule("propose_only"),
            a_rule("act_and_report", kind="capability", capability="unlock_guest"),
        ],
        "freezes": [
            {
                "name": "backups",
                "scope": {"kind": "resource", "resource_id": "tank"},
                "start": "01:00",
                "end": "04:00",
                "timezone": "Europe/Lisbon",
                "reason": "backups run",
            }
        ],
        "budgets": [{"name": "hourly", "counted_by": "resource", "limit": 3}],
        "overrides": [],
    }

    written = await client.put(POLICY, json=document, headers=bearer(secret))
    assert written.status_code == 200

    read = await client.get(POLICY, headers=bearer(secret))
    assert read.status_code == 200
    body = read.json()
    assert [rule["level"] for rule in body["rules"]] == ["propose_only", "act_and_report"]
    assert body["freezes"][0]["timezone"] == "Europe/Lisbon"
    assert body["budgets"][0]["limit"] == 3


@pytest.mark.parametrize(
    ("document", "named"),
    [
        ({"rules": [{"scope": {"kind": "galaxy"}, "level": "act_and_report"}]}, "kind"),
        ({"rules": [{"scope": {"kind": "resource"}, "level": "act_and_report"}]}, "scope"),
        ({"rules": [{"scope": {"kind": "deployment"}, "level": "run_wild"}]}, "level"),
        (
            {
                "freezes": [
                    {
                        "name": "backups",
                        "scope": {"kind": "deployment"},
                        "start": "1am",
                        "end": "04:00",
                    }
                ]
            },
            "start",
        ),
    ],
)
async def test_a_malformed_policy_is_refused_before_anything_is_stored(
    deployment: tuple[AsyncClient, GatewayState, str],
    document: dict[str, Any],
    named: str,
) -> None:
    client, _, secret = deployment
    response = await client.put(POLICY, json=document, headers=bearer(secret))

    assert response.status_code == 400
    assert named in response.text

    unchanged = await client.get(POLICY, headers=bearer(secret))
    assert unchanged.json()["rules"] == []


async def test_explaining_an_action_returns_the_level_and_every_rule_considered(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    await client.put(
        POLICY,
        json={
            "rules": [
                a_rule("propose_only"),
                a_rule("act_and_report", kind="resource", resource_id="ct-101"),
            ]
        },
        headers=bearer(secret),
    )

    response = await client.post(
        f"{POLICY}/explain",
        json={
            "capability": "restart_workload",
            "subjects": [{"resource_id": "ct-101", "kind": "container"}],
            "risk_class": "low",
            "has_rollback_plan": True,
            "operation": "pct reboot 101",
        },
        headers=bearer(secret),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "act_and_report"
    assert body["decision"] == "execute"
    assert body["winning_rule"] == "resource:::ct-101::"
    assert {entry["rule_id"] for entry in body["considered"]} == {
        "deployment:::::",
        "resource:::ct-101::",
    }
    assert body["operation"] == "pct reboot 101"


async def test_an_action_with_no_declared_risk_class_explains_as_the_highest(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    await client.put(
        POLICY,
        json={
            "rules": [
                {
                    "scope": {"kind": "deployment"},
                    "level": "act_on_low_risk",
                    "risk_bound": "low",
                }
            ]
        },
        headers=bearer(secret),
    )

    response = await client.post(
        f"{POLICY}/explain",
        json={"capability": "unknown_tool", "subjects": [{"resource_id": "ct-101"}]},
        headers=bearer(secret),
    )

    body = response.json()
    assert body["risk_class"] == "critical"
    assert body["decision"] == "approve"


async def test_the_bounds_view_reports_the_freezes_budgets_and_the_stop(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, state, secret = deployment
    await client.put(
        POLICY,
        json={
            "freezes": [
                {
                    "name": "backups",
                    "scope": {"kind": "deployment"},
                    "start": "01:00",
                    "end": "04:00",
                }
            ],
            "budgets": [{"name": "hourly", "limit": 2}],
        },
        headers=bearer(secret),
    )

    before = await client.get(f"{POLICY}/bounds", headers=bearer(secret))
    assert before.status_code == 200
    assert before.json()["stopped"] is False
    assert before.json()["freezes"][0]["name"] == "backups"
    assert before.json()["budgets"][0]["limit"] == 2

    engaged = await client.post(
        "/v1/autonomy/kill-switch",
        json={"reason": "the estate is on fire"},
        headers=bearer(secret),
    )
    assert engaged.status_code == 200
    assert engaged.json()["engaged"] is True
    assert state.kill_switch.is_engaged(team_node_id=TEAM_PAYMENTS)

    during = await client.get(f"{POLICY}/bounds", headers=bearer(secret))
    assert during.json()["stopped"] is True
    assert "the estate is on fire" in during.json()["stop_reason"]

    released = await client.delete("/v1/autonomy/kill-switch", headers=bearer(secret))
    assert released.status_code == 200
    assert released.json()["engaged"] is False


async def test_the_kill_switch_refuses_an_action_the_policy_would_have_run(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    await client.put(POLICY, json={"rules": [a_rule("act_and_report")]}, headers=bearer(secret))

    body = {
        "capability": "restart_workload",
        "subjects": [{"resource_id": "ct-101"}],
        "risk_class": "trivial",
    }
    before = await client.post(f"{POLICY}/explain", json=body, headers=bearer(secret))
    assert before.json()["decision"] == "execute"

    await client.post("/v1/autonomy/kill-switch", json={"reason": "stop"}, headers=bearer(secret))
    after = await client.post(f"{POLICY}/explain", json=body, headers=bearer(secret))

    assert after.json()["decision"] == "refuse"
    assert after.json()["refused_by"] == "kill_switch"


async def test_a_kill_switch_engaged_without_a_reason_is_refused_at_the_schema(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    response = await client.post("/v1/autonomy/kill-switch", json={}, headers=bearer(secret))
    assert response.status_code == 422


async def test_turning_dry_run_on_simulates_without_changing_the_level(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    await client.put(POLICY, json={"rules": [a_rule("act_and_report")]}, headers=bearer(secret))

    response = await client.post(
        f"{POLICY}/dry-run", json={"enabled": True}, headers=bearer(secret)
    )
    assert response.status_code == 200
    assert response.json()["dry_run"] is True

    explained = await client.post(
        f"{POLICY}/explain",
        json={
            "capability": "restart_workload",
            "subjects": [{"resource_id": "ct-101"}],
            "risk_class": "trivial",
        },
        headers=bearer(secret),
    )
    assert explained.json()["decision"] == "simulate"
    assert explained.json()["level"] == "act_and_report"


async def test_an_override_raises_autonomy_and_reads_back_with_its_expiry(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    response = await client.post(
        f"{POLICY}/overrides",
        json={
            "name": "rack-move",
            "level": "act_and_report",
            "reason": "moving the rack",
            "seconds": 3600,
        },
        headers=bearer(secret),
    )
    assert response.status_code == 201
    assert response.json()["granted_by"] == "ada"
    assert response.json()["expires_at"]

    bounds = await client.get(f"{POLICY}/bounds", headers=bearer(secret))
    assert [entry["name"] for entry in bounds.json()["overrides"]] == ["rack-move"]

    explained = await client.post(
        f"{POLICY}/explain",
        json={
            "capability": "restart_workload",
            "subjects": [{"resource_id": "ct-101"}],
            "risk_class": "trivial",
        },
        headers=bearer(secret),
    )
    assert explained.json()["level"] == "act_and_report"


async def test_an_override_longer_than_the_ceiling_is_refused(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    response = await client.post(
        f"{POLICY}/overrides",
        json={
            "name": "forever",
            "level": "act_and_report",
            "reason": "no",
            "seconds": 60 * 60 * 48,
        },
        headers=bearer(secret),
    )
    assert response.status_code == 400
    assert "hours at most" in response.text


async def test_a_preview_over_recorded_history_reports_what_would_change(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, state, secret = deployment
    await _record_a_decision(state.gateway)

    response = await client.post(
        f"{POLICY}/preview",
        json={"rules": [a_rule("act_and_report", kind="labels", labels={"env": "lab"})]},
        headers=bearer(secret),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["considered"] == 1
    assert body["changed"] == 1
    assert body["newly_autonomous"] == 1
    assert body["actions"][0]["before"] == "propose_only"
    assert body["actions"][0]["after"] == "act_and_report"


async def test_a_preview_over_no_history_says_so(
    deployment: tuple[AsyncClient, GatewayState, str],
) -> None:
    client, _, secret = deployment
    response = await client.post(
        f"{POLICY}/preview", json={"rules": [a_rule("act_and_report")]}, headers=bearer(secret)
    )
    assert response.status_code == 200
    assert "no recorded history" in response.json()["summary"]


async def test_a_viewer_may_read_the_posture_and_may_not_change_it() -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )

    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=FakeInvestigationRunner()
    )
    secret = await issue_token(
        store, state.tokens, user_id="viewer", role=Role.VIEWER, node_id=TEAM_PAYMENTS
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        assert (await client.get(POLICY, headers=bearer(secret))).status_code == 200
        assert (await client.get(f"{POLICY}/bounds", headers=bearer(secret))).status_code == 200
        assert (
            await client.put(POLICY, json={"rules": []}, headers=bearer(secret))
        ).status_code == 403
        assert (
            await client.post(
                "/v1/autonomy/kill-switch", json={"reason": "no"}, headers=bearer(secret)
            )
        ).status_code == 403


async def _record_a_decision(gateway: PersistenceGateway) -> None:
    """Write one autonomy decision to the trail, the way the engine writes it."""
    from platform.autonomy.audit import DecisionAuditor
    from platform.autonomy.decision import AutonomyGate
    from platform.autonomy.risk import RiskClass
    from platform.autonomy.subjects import ProposedAction, Subject
    from platform.identity.audit.recorder import AuditRecorder

    scope = TenantScope(org_id=ORG)
    gate = AutonomyGate(
        auditor=DecisionAuditor(scope=scope, recorder=AuditRecorder(gateway=gateway)),
    )
    await gate.record(
        await gate.decide(
            ProposedAction(
                action_id="act-recorded",
                capability="restart_workload",
                subjects=(
                    Subject(
                        resource_id="ct-101",
                        kind="container",
                        labels={"env": "lab"},
                        team_node_id=TEAM_PAYMENTS,
                    ),
                ),
                risk_class=RiskClass.LOW,
                has_rollback_plan=True,
                requester="ada",
                team_node_id=TEAM_PAYMENTS,
            )
        )
    )
