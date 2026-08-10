"""Reading the emergency stop, which every viewer is entitled to.

Engaging it is a responder's act. *Knowing it is engaged* is everybody's: a
person looking at a dashboard where nothing is happening has to be able to tell
"nothing needed doing" from "every automated write is stopped", and those two
render identically until somebody says which it is.

There was no way to ask. `POST` and `DELETE` return the state as a side effect
of changing it, which answers the question only for the person who just changed
it — so a banner on every screen had nothing to read.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from config.constants.security import REMEDIATION_AUDIT_ACTION_KILL_SWITCH
from platform.identity.permissions import Role
from platform.persistence.ports.audit_repository import AuditOutcome
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio


async def _headers(deployment: Deployment, role: Role, user_id: str) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id=user_id, role=role, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def test_a_viewer_can_read_whether_automation_is_stopped(
    client: AsyncClient, deployment: Deployment
) -> None:
    answer = await client.get(
        "/v1/autonomy/kill-switch", headers=await _headers(deployment, Role.VIEWER, "vera")
    )

    assert answer.status_code == 200
    assert answer.json()["engaged"] is False


async def test_the_state_a_responder_engaged_is_the_state_a_viewer_reads(
    client: AsyncClient, deployment: Deployment
) -> None:
    await client.post(
        "/v1/autonomy/kill-switch",
        headers=await _headers(deployment, Role.RESPONDER, "rosa"),
        json={"reason": "the storage controller is lying about free space"},
    )

    answer = await client.get(
        "/v1/autonomy/kill-switch", headers=await _headers(deployment, Role.VIEWER, "vera")
    )

    assert answer.json()["engaged"] is True


async def test_releasing_it_is_visible_to_a_viewer_too(
    client: AsyncClient, deployment: Deployment
) -> None:
    responder = await _headers(deployment, Role.RESPONDER, "rosa")
    await client.post("/v1/autonomy/kill-switch", headers=responder, json={"reason": "stop"})
    await client.delete("/v1/autonomy/kill-switch", headers=responder)

    answer = await client.get(
        "/v1/autonomy/kill-switch", headers=await _headers(deployment, Role.VIEWER, "vera")
    )

    assert answer.json()["engaged"] is False


async def test_a_viewer_still_cannot_engage_it(client: AsyncClient, deployment: Deployment) -> None:
    # Reading is everybody's; stopping the deployment is not. The two are
    # separate rows in the route table for exactly this reason.
    answer = await client.post(
        "/v1/autonomy/kill-switch",
        headers=await _headers(deployment, Role.VIEWER, "vera"),
        json={"reason": "curiosity"},
    )

    assert answer.status_code == 403


async def test_engaging_it_leaves_an_audit_row_naming_who_stopped_what(
    client: AsyncClient, deployment: Deployment
) -> None:
    # The most consequential write this deployment has: everything automated
    # stops. A stop with no record is a stop nobody can attribute afterwards,
    # and "who stopped remediation last Tuesday" is asked in every review of a
    # night that went wrong.
    await client.post(
        "/v1/autonomy/kill-switch",
        headers=await _headers(deployment, Role.RESPONDER, "rosa"),
        json={"reason": "the storage controller is lying about free space"},
    )

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    stops = [event for event in events if event.action == REMEDIATION_AUDIT_ACTION_KILL_SWITCH]
    assert len(stops) == 1
    assert stops[0].actor_id == "rosa"
    assert stops[0].outcome is AuditOutcome.ALLOWED
    assert stops[0].detail["engaged"] is True


async def test_releasing_it_is_audited_too_because_that_is_the_sensitive_direction(
    client: AsyncClient, deployment: Deployment
) -> None:
    # A release is the moment automated writes become possible again. A trail
    # that recorded only stops would leave every restart unattributed.
    responder = await _headers(deployment, Role.RESPONDER, "rosa")
    await client.post("/v1/autonomy/kill-switch", headers=responder, json={"reason": "stop"})
    await client.delete("/v1/autonomy/kill-switch", headers=responder)

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    releases = [
        event
        for event in events
        if event.action == REMEDIATION_AUDIT_ACTION_KILL_SWITCH
        and event.detail.get("engaged") is False
    ]
    assert len(releases) == 1
    assert releases[0].actor_id == "rosa"
