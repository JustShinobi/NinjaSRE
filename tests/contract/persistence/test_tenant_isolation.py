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
    EffectivenessQuery,
    Episode,
    EstateQuery,
    HealthDerivation,
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    KnowledgeDocument,
    PayloadSample,
    PersistenceGateway,
    RecurringProblem,
    ReferenceKind,
    RemediationOutcome,
    Resource,
    ResourceHealth,
    ResourceReference,
    ScheduledJob,
    SecretValue,
    SessionRecord,
    Signal,
    SignalKind,
    SignalQuery,
    StoredStrategy,
    SweepOutcome,
    SweepRecord,
    TenantScope,
    TimelineEntry,
    TimelineKind,
    TopologyEdge,
    TraceEventRecord,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
    UnitOfWork,
    User,
)
from platform.persistence.ports.signal_store import signal_key

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
        "estate",
        "signals",
        "incidents",
        "remediation",
        "transit",
    }
)


async def write_one_of_everything(uow: UnitOfWork) -> None:
    """Write a record through all seventeen tenant-scoped ports."""
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
    await uow.run_traces.record_event(
        TraceEventRecord(event_id="ev-1", run_id="run-1", kind="run_started", occurred_at=at())
    )
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
    await uow.estate.upsert(
        Resource(
            resource_id="res-1",
            kind="virtual_machine",
            source="proxmox",
            native_id="qemu/101",
            display_name="checkout-api",
            first_seen_at=at(),
            last_seen_at=at(),
        )
    )
    await uow.estate.record_health(
        "res-1",
        HealthDerivation(state=ResourceHealth.HEALTHY, rule="provider_status", derived_at=at()),
    )
    await uow.estate.link(
        ResourceReference(
            resource_id="res-1",
            reference_kind=ReferenceKind.RUN,
            reference_id="run-1",
            recorded_at=at(),
        )
    )
    await uow.estate.record_sweep(
        SweepRecord(
            sweep_id="sw-1",
            source="proxmox",
            started_at=at(),
            outcome=SweepOutcome.SUCCEEDED,
            completed_at=at(1),
            seen_count=1,
        )
    )
    incident = Incident(
        incident_id="inc-1",
        correlation_key="detector:datastore-near-full",
        title="Datastore near full",
        summary="res-1 is 95.65% full",
        origin=IncidentOrigin.DETECTOR,
        origin_id="datastore-near-full",
        severity="critical",
        state=IncidentState.OPEN,
        opened_at=at(),
        subjects=(IncidentSubject(resource_id="res-1", detail="95.65% full"),),
    )
    await uow.incidents.upsert(incident)
    await uow.incidents.append(
        (
            TimelineEntry(
                entry_id="inc-1@opened",
                incident_id="inc-1",
                kind=TimelineKind.OPENED,
                at=at(),
                cause="the condition held for its declared duration",
            ),
        )
    )
    await uow.signals.append(
        [
            Signal(
                signal_id=signal_key("storage.used_percent", "res-1", at()),
                name="storage.used_percent",
                resource_id="res-1",
                source="poller:proxmox",
                kind=SignalKind.NUMBER,
                observed_at=at(),
                value=91.0,
                interval_seconds=60,
            )
        ]
    )
    await uow.remediation.record(
        RemediationOutcome(
            action_id="action-1",
            capability="clear_cache",
            resource_id="res-1",
            executed_at=at(),
            due_at=at(5),
            condition_key="datastore-near-full",
        )
    )
    await uow.transit.record(
        TransitDelivery(
            delivery_id="alertmanager-1",
            direction=TransitDirection.INGRESS,
            source="alertmanager",
            occurred_at=at(),
            outcome=TransitOutcome.ACCEPTED,
        )
    )
    await uow.transit.store_sample(
        PayloadSample(
            source="alertmanager",
            captured_at=at(),
            body='{"status": "firing"}',
            masking_policy="standard",
        )
    )
    await uow.remediation.upsert_problem(
        RecurringProblem(
            problem_id="problem-1",
            pattern_key="clear_cache@res-1",
            capability="clear_cache",
            resource_id="res-1",
            title="clear_cache keeps being applied to res-1",
            summary="Four applications in thirty days.",
            raised_at=at(),
            occurrences=4,
            window_seconds=2_592_000,
        )
    )


@pytest.fixture
async def populated(gateway: PersistenceGateway) -> PersistenceGateway:
    """Return a gateway with one record of every kind, owned by ``acme``."""
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await write_one_of_everything(uow)
    return gateway


async def test_the_other_tenant_sees_none_of_it(populated: PersistenceGateway) -> None:
    async with populated.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        assert await uow.estate.get("res-1") is None
        assert await uow.estate.query(EstateQuery()) == ()
        assert await uow.estate.by_native_id(source="proxmox", native_id="qemu/101") is None
        assert (await uow.estate.summarise(now=at())).total == 0
        assert await uow.estate.transitions("res-1") == ()
        assert await uow.estate.references("res-1") == ()
        assert await uow.estate.last_sweep("proxmox") is None
        assert await uow.signals.window(SignalQuery()) == ()
        assert await uow.signals.latest() == ()
        assert await uow.signals.prune(before=at(10)) == 0
        assert await uow.incidents.get("inc-1") is None
        assert await uow.incidents.query(IncidentQuery()) == ()
        assert await uow.incidents.open_for("detector:datastore-near-full") is None
        assert await uow.incidents.timeline("inc-1") == ()
        assert await uow.incidents.purge(before=at(10)) == 0
        assert await uow.remediation.get("action-1") is None
        assert await uow.remediation.history(EffectivenessQuery()) == ()
        assert (await uow.remediation.effectiveness(EffectivenessQuery())).total == 0
        assert await uow.remediation.open_problem_for("clear_cache@res-1") is None
        assert await uow.remediation.problems() == ()
        assert await uow.remediation.purge(before=at(10)) == 0
        assert await uow.transit.delivery("alertmanager-1") is None
        assert await uow.transit.deliveries(TransitQuery()) == ()
        assert await uow.transit.sample("alertmanager") is None
        assert await uow.transit.activity(direction=TransitDirection.INGRESS, since=at()) == ()
        assert await uow.transit.prune(before=at(10)) == 0
        assert (
            await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(10))
        ) == ()
        assert await uow.estate.mark_stale(source="proxmox", at=at(10), reason="down") == ()
        assert await uow.config.get("payments") is None
        assert await uow.config.children(SECOND_ORG) == ()
        assert await uow.identity.tokens_for_user("u-ada") == ()
        assert await uow.identity.list_tokens() == ()
        assert await uow.identity.record_token_use("t-1", used_at=at()) is False
        assert await uow.identity.revoke_tokens(("t-1",), revoked_at=at()) == ()
        assert await uow.audit.get("e-1") is None
        assert await uow.audit.query() == ()
        assert await uow.run_traces.get_run("run-1") is None
        assert await uow.run_traces.list_runs() == ()
        assert await uow.run_traces.events_for_run("run-1") == ()
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
        edges = await uow.topology.edges_from("web")
        removed = await uow.topology.delete_edge(
            TopologyEdge(from_node_id="web", to_node_id="checkout")
        )

    assert dependents.nodes == ()
    # The edge-shaped half of the catalogue is scoped like everything else: the
    # other tenant's edge is neither readable nor deletable from here.
    assert edges == ()
    assert removed is False

    async with populated.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        assert [edge.to_node_id for edge in await uow.topology.edges_from("web")] == ["checkout"]


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
        assert await uow.estate.get("res-1") is not None
        assert len(await uow.signals.latest()) == 1
        assert await uow.incidents.get("inc-1") is not None
        assert await uow.remediation.get("action-1") is not None
        assert await uow.remediation.open_problem_for("clear_cache@res-1") is not None


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
