"""Contract: nothing written in one organisation is reachable from another.

SC-006 and FR-010. The design claim is stronger than "cross-tenant reads are
rejected": no port method takes an organisation argument, so a cross-tenant read
cannot be *phrased*. That claim is worth very little without a test that tries,
because the way it would break is somebody adding a method that takes an id and
looks it up globally — which compiles, passes its own suite, and is a data leak.

So this file writes one record through every tenant-scoped port as ``acme``, then
opens ``globex`` and goes looking. Adding a port without adding it here means
``test_every_tenant_scoped_port_is_covered`` fails, which is the part that keeps
this file honest as the package grows.
"""

from __future__ import annotations

import pytest
from conftest import PRIMARY_ORG, SECOND_ORG, at

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from config.constants.security import SIDE_EFFECT_WRITE_REVERSIBLE
from platform.persistence.errors import RecordNotFound, VectorNamespaceUnknown
from platform.persistence.ports import (
    ActorKind,
    AgentRun,
    ApiToken,
    ApprovalRequest,
    AuditEvent,
    ConfigNode,
    ConfigNodeKind,
    CredentialMetadata,
    Episode,
    KnowledgeDocument,
    PersistenceGateway,
    ScheduledJob,
    SecretValue,
    SessionRecord,
    StoredStrategy,
    TenantScope,
    TopologyEdge,
    UnitOfWork,
    User,
)

pytestmark = pytest.mark.contract

#: Every repository on ``UnitOfWork``. A port added without a case below fails
#: the coverage test at the bottom rather than quietly going unchecked.
TENANT_SCOPED_PORTS = frozenset(
    {
        "config",
        "identity",
        "audit",
        "run_traces",
        "sessions",
        "episodes",
        "vectors",
        "topology",
        "knowledge",
        "approvals",
        "schedules",
        "credentials",
    }
)


async def write_one_of_everything(uow: UnitOfWork) -> None:
    """Write a record through all twelve tenant-scoped ports."""
    await uow.config.upsert(
        ConfigNode(
            node_id="payments",
            kind=ConfigNodeKind.TEAM,
            name="payments",
            parent_id=uow.scope.org_id,
        )
    )
    await uow.identity.upsert_user(
        User(user_id="u-ada", email="ada@example.com", display_name="Ada")
    )
    await uow.identity.store_token(
        ApiToken(token_id="t-1", user_id="u-ada", name="laptop", token_hash="sha256:aaa")
    )
    await uow.audit.append(
        AuditEvent(
            event_id="e-1",
            occurred_at=at(),
            actor_kind=ActorKind.AGENT,
            actor_id="run-1",
            action="capability.invoke",
            resource_kind="deployment",
            resource_id="checkout",
        )
    )
    await uow.run_traces.start_run(AgentRun(run_id="run-1", trigger="alert", started_at=at()))
    await uow.sessions.save(SessionRecord(session_id="s-1", status="suspended"))
    await uow.episodes.save(
        Episode(
            episode_id="ep-1",
            title="Checkout 5xx",
            summary="Pool exhaustion.",
            signature="checkout-5xx",
            occurred_at=at(),
        )
    )
    await uow.episodes.save_strategy(
        StoredStrategy(
            team_node_id="payments",
            issue_type="connection_pool_exhaustion",
            component_key="service:checkout",
            content={"common_root_causes": ["a retry storm"]},
            generated_at=at(),
        )
    )
    await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model="m", dimension=2)
    await uow.topology.upsert_edge(TopologyEdge(from_node_id="web", to_node_id="checkout"))
    await uow.knowledge.upsert_document(
        KnowledgeDocument(document_id="doc-1", title="Runbook", checksum="sha256:v1")
    )
    await uow.approvals.create_request(
        ApprovalRequest(
            approval_id="a-1",
            run_id="run-1",
            action="kubernetes.restart_deployment",
            side_effect_level=SIDE_EFFECT_WRITE_REVERSIBLE,
            summary="Restart checkout.",
            requested_at=at(),
            expires_at=at(30),
        )
    )
    await uow.schedules.upsert_job(
        ScheduledJob(job_id="j-1", name="sync", kind="knowledge.sync", schedule="0 2 * * *")
    )
    await uow.credentials.store(
        CredentialMetadata(handle="slack-bot-token", integration="slack"),
        SecretValue("xoxb-not-a-real-token"),
    )


@pytest.fixture
async def populated(gateway: PersistenceGateway) -> PersistenceGateway:
    """Return a gateway with one record of every kind, owned by ``acme``."""
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await write_one_of_everything(uow)
    return gateway


async def test_the_other_tenant_sees_none_of_it(populated: PersistenceGateway) -> None:
    async with populated.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        assert await uow.config.get("payments") is None
        assert await uow.config.children(SECOND_ORG) == ()
        assert await uow.identity.tokens_for_user("u-ada") == ()
        assert await uow.audit.get("e-1") is None
        assert await uow.audit.query() == ()
        assert await uow.run_traces.get_run("run-1") is None
        assert await uow.run_traces.list_runs() == ()
        assert await uow.sessions.load("s-1") is None
        assert await uow.episodes.get("ep-1") is None
        assert await uow.episodes.count() == 0
        assert await uow.episodes.list_strategies(team_node_id="payments") == ()
        assert (
            await uow.episodes.get_strategy(
                team_node_id="payments",
                issue_type="connection_pool_exhaustion",
                component_key="service:checkout",
            )
            is None
        )
        assert await uow.knowledge.get_document("doc-1") is None
        assert await uow.approvals.get_request("a-1") is None
        assert await uow.approvals.list_pending() == ()
        assert await uow.schedules.get_job("j-1") is None
        assert await uow.credentials.get_metadata("slack-bot-token") is None
        assert await uow.credentials.list_metadata() == ()


async def test_a_vector_namespace_is_not_shared_between_tenants(
    populated: PersistenceGateway,
) -> None:
    # Two organisations declaring a namespace with the same name get two
    # indexes, and neither can search the other's.
    async with populated.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        assert await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE) is None

        with pytest.raises(VectorNamespaceUnknown):
            await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, (1.0, 0.0))


async def test_topology_is_not_shared_between_tenants(
    populated: PersistenceGateway,
) -> None:
    async with populated.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        dependents = await uow.topology.direct_dependents("checkout")

    assert dependents.nodes == ()


async def test_a_record_that_exists_elsewhere_is_missing_here_not_forbidden(
    populated: PersistenceGateway,
) -> None:
    # The error must not distinguish "another tenant has this" from "nobody
    # does". Reporting the difference would be the leak the scoping prevents.
    async with populated.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        with pytest.raises(RecordNotFound) as elsewhere:
            await uow.run_traces.replay("run-1")
        with pytest.raises(RecordNotFound) as nowhere:
            await uow.run_traces.replay("run-never-existed")

    assert type(elsewhere.value) is type(nowhere.value)
    assert PRIMARY_ORG not in str(elsewhere.value)


async def test_the_first_tenant_still_has_everything(
    populated: PersistenceGateway,
) -> None:
    # The isolation assertions above would all pass against a store that lost
    # the writes.
    async with populated.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        assert await uow.config.get("payments") is not None
        assert await uow.run_traces.get_run("run-1") is not None
        assert await uow.episodes.count() == 1
        assert await uow.episodes.list_strategies(team_node_id="payments") != ()
        assert await uow.credentials.get_metadata("slack-bot-token") is not None


def test_every_tenant_scoped_port_is_covered() -> None:
    """Fail when a port is added without an isolation case above.

    Read off the protocol rather than off an implementation. A backend is
    entitled to whatever attributes it needs — the Postgres unit of work carries
    a session and the graph's readiness — and asserting against those would make
    this test about the backend instead of about the contract.
    """
    exposed = {
        name
        for name in dir(UnitOfWork)
        if not name.startswith("_")
        and name not in {"scope", "mark_rollback_only", "is_rollback_only"}
    }

    assert exposed == TENANT_SCOPED_PORTS
