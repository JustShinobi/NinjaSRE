"""The audit listing and its own count, over HTTP.

A caller who narrowed the listing with a filter and a caller who asked how many
events exist under that same filter are asking the same question, and the
answers have to agree — the count is not a second, wider query over the raw
window.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from platform.persistence.ports.audit_repository import ActorKind, AuditEvent
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

EVENTS = "/audit/events"


async def _owner(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


def _event(event_id: str, *, action: str, actor_id: str = "ada") -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        occurred_at=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        actor_kind=ActorKind.USER,
        actor_id=actor_id,
        action=action,
        resource_kind="grant",
        resource_id="grant-1",
    )


async def test_the_total_counts_what_the_filtered_listing_returned(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.audit.append(_event("aud-1", action="permission.grant"))
        await uow.audit.append(_event("aud-2", action="permission.revoke"))

    answer = await client.get(
        EVENTS, params={"action": "permission.grant"}, headers=await _owner(deployment)
    )

    assert answer.status_code == 200
    body = answer.json()
    assert len(body["events"]) == 1
    # The defect this reproduces: a filtered listing of one event reported by a
    # total counting the whole window (two), rather than the same question the
    # listing itself answered.
    assert body["total"] == len(body["events"]) == 1


async def test_the_total_still_counts_the_whole_window_when_nothing_narrows_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    # Issuing the owner's own bearer token is itself an audited event, so the
    # baseline is read after it rather than assumed to be zero.
    headers = await _owner(deployment)
    baseline = (await client.get(EVENTS, headers=headers)).json()["total"]

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.audit.append(_event("aud-1", action="permission.grant"))
        await uow.audit.append(_event("aud-2", action="permission.revoke"))

    answer = await client.get(EVENTS, headers=headers)

    assert answer.json()["total"] == baseline + 2
