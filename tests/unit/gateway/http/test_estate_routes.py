"""The estate over HTTP: five routes, and the two things a client must not do.

A client must not compute freshness — so every response carries the reported
state, already overlaid — and a client must not invent a health value, so a
filter naming one the closed set does not hold is refused rather than ignored.
Everything else here is the ordinary shape of a read surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from config.constants.estate import MAX_ESTATE_PAGE_SIZE, MAX_MAINTENANCE_SECONDS
from platform.identity.permissions import Role
from platform.persistence.ports.estate_repository import (
    HealthDerivation,
    HealthSignal,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
    ResourceSource,
)
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio


def _now() -> datetime:
    """Return an instant recent enough that nothing seeded here reads as stale."""
    return datetime.now(UTC)


async def _headers(deployment: Deployment, role: Role = Role.OWNER) -> dict[str, str]:
    """Return the authorisation header for a principal holding ``role``."""
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id=f"u-{role.value}", role=role, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _seed(deployment: Deployment) -> None:
    """Write a node, two guests hanging off it, and one that has gone."""
    now = _now()
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-node",
                kind="node",
                source="proxmox",
                native_id="node/pve1",
                display_name="pve1",
                labels=("site:home",),
                sources=(ResourceSource(integration="proxmox", native_id="node/pve1"),),
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        for resource_id, native, state in (
            ("res-ok", "qemu/101", ResourceHealth.HEALTHY),
            ("res-bad", "qemu/102", ResourceHealth.UNHEALTHY),
        ):
            await uow.estate.upsert(
                Resource(
                    resource_id=resource_id,
                    kind="virtual_machine",
                    source="proxmox",
                    native_id=native,
                    display_name=native,
                    parent_id="res-node",
                    labels=("env:prod",),
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            await uow.estate.record_health(
                resource_id,
                HealthDerivation(
                    state=state,
                    rule="provider_status",
                    derived_at=now,
                    raw_status="running" if state is ResourceHealth.HEALTHY else "stopped",
                    explanation=f"the provider reported {state.value}",
                    signals=(
                        HealthSignal(
                            name="provider_status",
                            value=state.value,
                            observed_at=now,
                            source="proxmox",
                        ),
                    ),
                ),
            )
        await uow.estate.record_health(
            "res-node",
            HealthDerivation(
                state=ResourceHealth.HEALTHY,
                rule="provider_status",
                derived_at=now,
                raw_status="online",
            ),
        )
        await uow.estate.link(
            ResourceReference(
                resource_id="res-bad",
                reference_kind=ReferenceKind.RUN,
                reference_id="run-9",
                recorded_at=now,
                summary="investigated the stopped guest",
            )
        )
        await uow.estate.upsert(
            Resource(
                resource_id="res-gone",
                kind="container",
                source="docker",
                native_id="ct/7",
                display_name="old-cache",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        await uow.estate.mark_absent(source="docker", seen_ids=frozenset(), at=now)


# --- The listing ---------------------------------------------------------------


async def test_the_estate_lists_what_is_present_and_omits_what_is_gone(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)

    response = await client.get("/v1/estate/resources", headers=await _headers(deployment))

    assert response.status_code == 200
    found = {row["resource_id"]: row for row in response.json()["resources"]}
    assert set(found) == {"res-node", "res-ok", "res-bad"}
    assert found["res-ok"]["health"] == "healthy"
    assert found["res-bad"]["health"] == "unhealthy"
    assert found["res-ok"]["explanation"]


async def test_an_absent_resource_is_reachable_when_it_is_asked_for(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)

    response = await client.get(
        "/v1/estate/resources",
        params={"include_absent": "true"},
        headers=await _headers(deployment),
    )

    rows = {row["resource_id"]: row for row in response.json()["resources"]}
    assert rows["res-gone"]["health"] == "absent"
    assert rows["res-gone"]["absent_since"] is not None


async def test_every_declared_dimension_is_a_query_parameter(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    headers = await _headers(deployment)

    async def ids(**params: str) -> set[str]:
        response = await client.get("/v1/estate/resources", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return {row["resource_id"] for row in response.json()["resources"]}

    assert await ids(kind="virtual_machine") == {"res-ok", "res-bad"}
    assert await ids(health="unhealthy") == {"res-bad"}
    assert await ids(source="proxmox") == {"res-node", "res-ok", "res-bad"}
    assert await ids(label="env:prod") == {"res-ok", "res-bad"}
    assert await ids(parent="res-node") == {"res-ok", "res-bad"}


async def test_a_health_filter_outside_the_closed_set_is_refused(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Ignoring it would answer "everything" to a question about "broken"."""
    response = await client.get(
        "/v1/estate/resources",
        params={"health": "broken"},
        headers=await _headers(deployment),
    )

    assert response.status_code == 422
    assert "health state" in response.json()["error"]["message"]


async def test_a_page_larger_than_the_bound_is_refused_rather_than_clamped(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.get(
        "/v1/estate/resources",
        params={"limit": str(MAX_ESTATE_PAGE_SIZE + 1)},
        headers=await _headers(deployment),
    )

    assert response.status_code == 422
    assert str(MAX_ESTATE_PAGE_SIZE) in response.json()["error"]["message"]


# --- The summary ---------------------------------------------------------------


async def test_the_summary_counts_the_estate_and_its_problems(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)

    response = await client.get("/v1/estate/summary", headers=await _headers(deployment))

    assert response.status_code == 200
    summary = response.json()
    assert summary["total"] == 3
    assert summary["absent"] == 1
    assert summary["problems"] == 1
    assert summary["by_kind"] == {"node": 1, "virtual_machine": 2}


# --- One resource --------------------------------------------------------------


async def test_a_resource_carries_its_derivation_its_history_and_what_touched_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance scenario 6, over HTTP."""
    await _seed(deployment)

    response = await client.get("/v1/estate/resources/res-bad", headers=await _headers(deployment))

    assert response.status_code == 200
    body = response.json()
    assert body["resource"]["health"] == "unhealthy"
    assert body["derivation"]["rule"] == "provider_status"
    assert body["derivation"]["raw_status"] == "stopped"
    assert body["derivation"]["signals"][0]["name"] == "provider_status"
    assert [entry["state"] for entry in body["transitions"]] == ["unhealthy"]
    assert body["references"][0]["reference_id"] == "run-9"
    assert body["parent"]["resource_id"] == "res-node"


async def test_a_parents_page_carries_the_children_its_health_accounts_for(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)

    response = await client.get("/v1/estate/resources/res-node", headers=await _headers(deployment))

    body = response.json()
    assert {child["resource_id"] for child in body["children"]} == {"res-ok", "res-bad"}
    assert body["rollup_rule"] == "majority_healthy"
    assert body["freshness_seconds"] > 0


async def test_a_resource_nobody_has_is_a_404(client: AsyncClient, deployment: Deployment) -> None:
    response = await client.get(
        "/v1/estate/resources/res-nobody", headers=await _headers(deployment)
    )

    assert response.status_code == 404


# --- Maintenance ---------------------------------------------------------------


async def test_maintenance_can_be_opened_and_closed(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    headers = await _headers(deployment)
    until = (_now() + timedelta(hours=2)).isoformat()

    opened = await client.post(
        "/v1/estate/resources/res-bad/maintenance",
        json={"until": until, "reason": "firmware upgrade"},
        headers=headers,
    )
    summary = await client.get("/v1/estate/summary", headers=headers)
    closed = await client.delete("/v1/estate/resources/res-bad/maintenance", headers=headers)

    assert opened.status_code == 200
    assert opened.json()["health"] == "maintenance"
    assert opened.json()["maintenance_reason"] == "firmware upgrade"
    # SC-008: in the estate, out of the problem count.
    assert summary.json()["total"] == 3
    assert summary.json()["problems"] == 0
    assert summary.json()["maintenance"] == 1
    assert closed.json()["health"] == "unhealthy"


async def test_a_maintenance_window_without_a_reason_is_refused(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)

    response = await client.post(
        "/v1/estate/resources/res-bad/maintenance",
        json={"until": (_now() + timedelta(hours=1)).isoformat(), "reason": ""},
        headers=await _headers(deployment),
    )

    assert response.status_code == 422


async def test_a_maintenance_window_past_the_bound_is_refused_rather_than_clamped(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    far = (_now() + timedelta(seconds=MAX_MAINTENANCE_SECONDS * 2)).isoformat()

    response = await client.post(
        "/v1/estate/resources/res-bad/maintenance",
        json={"until": far, "reason": "indefinitely"},
        headers=await _headers(deployment),
    )

    assert response.status_code == 422
    assert str(MAX_MAINTENANCE_SECONDS) in response.json()["error"]["message"]


# --- Permissions ---------------------------------------------------------------


async def test_a_viewer_may_read_the_estate_and_not_suppress_anything(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed(deployment)
    viewer = await _headers(deployment, Role.VIEWER)

    listing = await client.get("/v1/estate/resources", headers=viewer)
    suppress = await client.post(
        "/v1/estate/resources/res-bad/maintenance",
        json={"until": (_now() + timedelta(hours=1)).isoformat(), "reason": "no"},
        headers=viewer,
    )

    assert listing.status_code == 200
    assert suppress.status_code == 403


async def test_a_responder_may_open_a_maintenance_window(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The person working on the machine is the person who suppresses it."""
    await _seed(deployment)

    response = await client.post(
        "/v1/estate/resources/res-bad/maintenance",
        json={"until": (_now() + timedelta(hours=1)).isoformat(), "reason": "replacing a disk"},
        headers=await _headers(deployment, Role.RESPONDER),
    )

    assert response.status_code == 200


async def test_an_unauthenticated_caller_reaches_nothing(client: AsyncClient) -> None:
    missing = await client.get("/v1/estate/resources")
    invalid = await client.get(
        "/v1/estate/resources", headers={"authorization": "Bearer not-a-real-token"}
    )

    assert missing.status_code == 400
    assert invalid.status_code == 401
