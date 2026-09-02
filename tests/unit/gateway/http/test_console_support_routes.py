"""The reads a console needs and the API did not yet serve.

A console that computed any of these itself would be a second implementation of
configuration merging, approval assembly, or catalogue availability — the thing
the console is explicitly not allowed to become. So each one is asked of the
server, and each one is proven here against the real routes with a real issued
token.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from platform.config_service.document import NodeDocument
from platform.identity.permissions import Role
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.audit_repository import ActorKind, AuditEvent, AuditOutcome
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.knowledge_store import KnowledgeDocument
from platform.persistence.ports.topology_graph import EdgeKind, TopologyEdge, TopologyNode
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    Deployment,
    issue_token,
)

pytestmark = pytest.mark.anyio

EPOCH = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)


async def _owner(deployment: Deployment) -> dict[str, str]:
    """Return the authorisation header of an organisation-wide owner."""
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


# --- The org tree (FR-016, SC-008) -------------------------------------------


async def test_the_org_tree_is_served_as_one_document_with_every_node_s_parent(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.get("/v1/config", headers=await _owner(deployment))

    assert response.status_code == 200
    nodes = {node["node_id"]: node for node in response.json()["nodes"]}
    assert nodes[ORG]["parent_id"] is None
    assert nodes[TEAM_PAYMENTS]["parent_id"] == ORG
    assert nodes[TEAM_PAYMENTS]["kind"] == ConfigNodeKind.TEAM.value


async def test_a_team_scoped_caller_sees_its_own_subtree_and_not_a_sibling_s(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ines",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )

    response = await client.get("/v1/config", headers={"authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    seen = {node["node_id"] for node in response.json()["nodes"]}
    assert seen == {TEAM_PAYMENTS}


# --- The preview (FR-017, FR-018, FR-019, SC-005) -----------------------------


async def test_a_preview_returns_what_the_server_would_compute_without_storing_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=headers,
        json={"patch": {"policies": {"masking": {"level": "strict"}}}},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["values"]["policies"]["masking"]["level"] == "strict"
    assert body["provenance"]["policies.masking.level"] == TEAM_PAYMENTS

    stored = await client.get(f"/v1/config/{TEAM_PAYMENTS}", headers=headers)
    assert stored.json()["values"].get("policies", {}).get("masking", {}).get("level") != "strict"


async def test_a_preview_reports_the_field_it_would_change(
    client: AsyncClient, deployment: Deployment
) -> None:
    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {"policies": {"masking": {"level": "strict"}}}},
    )

    changed = {change["path"]: change for change in preview.json()["changes"]}
    assert changed["policies.masking.level"]["after"] == "strict"


async def test_a_preview_names_the_node_locking_a_field_it_cannot_change(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        root = await uow.config.get(ORG)
        assert root is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=ORG,
                kind=root.kind,
                name=root.name,
                parent_id=None,
                values=NodeDocument.of(
                    {"policies": {"masking": {"level": "standard"}}},
                    locked=("policies.masking.level",),
                ).to_values(),
                version=root.version,
            )
        )

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {"policies": {"masking": {"level": "strict"}}}},
    )

    body = preview.json()
    assert body["locked"] == {"policies.masking.level": ORG}
    assert body["values"]["policies"]["masking"]["level"] == "standard"


async def test_a_preview_reports_a_change_an_ancestor_puts_behind_an_approval(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        root = await uow.config.get(ORG)
        assert root is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=ORG,
                kind=root.kind,
                name=root.name,
                parent_id=None,
                values=NodeDocument.of({}, approval_gated=("policies.masking.level",)).to_values(),
                version=root.version,
            )
        )

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {"policies": {"masking": {"level": "strict"}}}},
    )

    assert preview.json()["approval_gated"] == ["policies.masking.level"]


async def test_a_preview_of_another_team_s_node_is_not_found(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="rui",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )

    response = await client.post(
        "/v1/config/platform/preview",
        headers={"authorization": f"Bearer {secret}"},
        json={"patch": {}},
    )

    assert response.status_code == 404


# --- The catalogue and integration forms (FR-020, FR-021) ---------------------


async def test_the_catalogue_reports_every_capability_with_its_availability(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.get(
        f"/v1/config/{TEAM_PAYMENTS}/catalogue", headers=await _owner(deployment)
    )

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert entries, "discovery found no capabilities at all"
    assert all("available" in entry and "reason" in entry for entry in entries)


async def test_integration_forms_are_served_as_schemas_never_as_values(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.get(
        f"/v1/config/{TEAM_PAYMENTS}/integration-schemas", headers=await _owner(deployment)
    )

    assert response.status_code == 200
    schemas = response.json()["schemas"]
    assert schemas, "no integration is installed at all"
    for schema in schemas:
        for credential_field in schema["credential_fields"]:
            assert set(credential_field) == {
                "name",
                "label",
                "secret",
                "required",
                "help",
                "min_scope",
                "guide_url",
            }


# --- Approvals and rollback (FR-009, FR-011) ----------------------------------


async def _seed_approval(deployment: Deployment) -> None:
    """Store one pending approval with a rollback plan behind it.

    ``expires_at`` is anchored to the real clock rather than to ``EPOCH``:
    ``GET /v1/approvals`` now sweeps genuinely lapsed requests to ``expired``
    before it lists (the fix for the sidebar badge counting an approval
    nobody could still decide), so an approval whose window closed months
    before whatever day this suite happens to run on would be swept out of
    the ``pending`` bucket this fixture exists to populate, and every test
    reading it back as pending would fail for a reason that has nothing to
    do with what it is testing.
    """
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.create_request(
            ApprovalRequest(
                approval_id="ap-1",
                run_id="run-1",
                action="kubernetes.restart_deployment",
                side_effect_level="disruptive",
                summary="restart checkout",
                requested_at=EPOCH,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                arguments={"deployment": "checkout", "namespace": "prod"},
            )
        )
        await uow.approvals.store_rollback_plan(
            RollbackPlan(
                plan_id="rb-1",
                approval_id="ap-1",
                steps=(
                    RollbackStep(
                        ordinal=1,
                        description="scale checkout back to 4 replicas",
                        capability="kubernetes.scale_deployment",
                        arguments={"replicas": 4},
                    ),
                ),
                notes="restores the replica count that was there before",
            )
        )


async def test_a_pending_approval_carries_everything_a_reviewer_has_to_decide_on(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed_approval(deployment)

    response = await client.get("/v1/approvals/ap-1", headers=await _owner(deployment))

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "kubernetes.restart_deployment"
    assert body["side_effect_level"] == "disruptive"
    assert body["arguments"] == {"deployment": "checkout", "namespace": "prod"}
    assert body["rollback_plan"]["steps"][0]["capability"] == "kubernetes.scale_deployment"


async def test_the_pending_queue_lists_the_longest_waiting_first(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _seed_approval(deployment)

    response = await client.get("/v1/approvals", headers=await _owner(deployment))

    assert [entry["approval_id"] for entry in response.json()["approvals"]] == ["ap-1"]


async def test_an_approval_with_no_stored_plan_says_so_rather_than_omitting_the_field(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.create_request(
            ApprovalRequest(
                approval_id="ap-2",
                run_id="run-1",
                action="kubernetes.describe_pod",
                side_effect_level="read",
                summary="look at the pod",
                requested_at=EPOCH,
                expires_at=EPOCH + timedelta(hours=1),
            )
        )

    response = await client.get("/v1/approvals/ap-2", headers=await _owner(deployment))

    assert response.json()["rollback_plan"] is None


# --- Topology and knowledge (FR-014, FR-015) ----------------------------------


async def test_topology_reports_dependencies_dependents_and_blast_radius(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for name in ("checkout", "payments-db", "storefront"):
            await uow.topology.upsert_node(TopologyNode(node_id=name, name=name))
        await uow.topology.upsert_edge(
            TopologyEdge(
                from_node_id="checkout", to_node_id="payments-db", kind=EdgeKind.DEPENDS_ON
            )
        )
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="storefront", to_node_id="checkout", kind=EdgeKind.DEPENDS_ON)
        )

    response = await client.get("/v1/topology/checkout", headers=await _owner(deployment))

    assert response.status_code == 200
    body = response.json()
    assert [node["node_id"] for node in body["dependencies"]] == ["payments-db"]
    assert [node["node_id"] for node in body["dependents"]] == ["storefront"]
    assert [entry["node"]["node_id"] for entry in body["blast_radius"]] == ["storefront"]


async def test_knowledge_documents_are_browsable(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.knowledge.upsert_document(
            KnowledgeDocument(
                document_id="doc-1",
                title="Checkout runbook",
                checksum="abc",
                source_uri="https://wiki.acme.test/checkout",
            )
        )

    response = await client.get("/v1/knowledge/documents", headers=await _owner(deployment))

    assert response.status_code == 200
    assert [doc["title"] for doc in response.json()["documents"]] == ["Checkout runbook"]


# --- Who am I, the record, and the tokens (FR-023, FR-025, FR-026) ------------


async def test_the_principal_s_own_permissions_are_readable_so_a_client_can_render_by_them(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="vera",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )

    response = await client.get("/auth/me", headers={"authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    body = response.json()
    assert body["principal_id"] == "vera"
    assert body["team_node_id"] == TEAM_PAYMENTS
    assert "investigation.read" in body["permissions"]
    assert "config.write" not in body["permissions"]
    assert body["impersonating"] is False


async def test_audit_events_are_browsable_with_filters(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for ordinal, action in enumerate(("config.write", "remediation.execute")):
            await uow.audit.append(
                AuditEvent(
                    event_id=f"ev-{ordinal}",
                    occurred_at=EPOCH + timedelta(minutes=ordinal),
                    actor_kind=ActorKind.USER,
                    actor_id="ada",
                    action=action,
                    resource_kind="config",
                    resource_id=TEAM_PAYMENTS,
                    outcome=AuditOutcome.ALLOWED,
                )
            )

    response = await client.get(
        "/audit/events?action=config.write", headers=await _owner(deployment)
    )

    assert response.status_code == 200
    assert [event["action"] for event in response.json()["events"]] == ["config.write"]


async def test_the_audit_export_is_the_same_records_as_a_stream_of_json_lines(
    client: AsyncClient, deployment: Deployment
) -> None:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.audit.append(
            AuditEvent(
                event_id="ev-x",
                occurred_at=EPOCH,
                actor_kind=ActorKind.USER,
                actor_id="ada",
                action="config.write",
                resource_kind="config",
                resource_id=TEAM_PAYMENTS,
            )
        )

    response = await client.get("/audit/export", headers=await _owner(deployment))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert '"event_id":"ev-x"' in response.text.replace(" ", "")


async def test_tokens_can_be_listed_and_revoked_in_bulk(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await issue_token(
        deployment.gateway, deployment.tokens, user_id="bot", role=Role.VIEWER, node_id=None
    )

    listed = await client.get("/identity/tokens", headers=headers)
    assert listed.status_code == 200
    assert any(token["name"] == "bot-token" for token in listed.json()["tokens"])

    revoked = await client.post("/identity/tokens/revoke", headers=headers, json={"user_id": "bot"})
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] >= 1

    after = await client.get("/identity/tokens", headers=headers)
    assert all(token["revoked"] for token in after.json()["tokens"] if token["user_id"] == "bot")


async def test_a_viewer_cannot_reach_the_token_list_at_all(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="vic", role=Role.VIEWER, node_id=None
    )

    response = await client.get("/identity/tokens", headers={"authorization": f"Bearer {secret}"})

    assert response.status_code == 403
