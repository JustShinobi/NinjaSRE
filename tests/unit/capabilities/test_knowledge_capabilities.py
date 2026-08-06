"""The three knowledge capabilities: what they declare, and what they refuse to imply.

The declarations are checked against the catalogue's rules because those rules
are what the scorer, the approval gate, and the console read — a tool that
reaches the catalogue having promised nothing is worse than one that is absent,
because it will be selected.

The outcomes are checked because they are deliberately distinct. Topology that
came back empty and topology that could not be reached lead to opposite
decisions. A proposal that was queued and a proposal that took effect are the
difference between a review workflow and a self-reinforcing loop, and the
capability's own receipt has to say which happened.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from capabilities.tools.system.knowledge_propose import binding as propose_binding
from capabilities.tools.system.knowledge_propose.tool import propose_knowledge
from capabilities.tools.system.knowledge_search import binding as search_binding
from capabilities.tools.system.knowledge_search import results as search_results
from capabilities.tools.system.knowledge_search.tool import search_knowledge_base
from capabilities.tools.system.topology_query import binding as topology_binding
from capabilities.tools.system.topology_query import results as topology_results
from capabilities.tools.system.topology_query.tool import query_service_topology
from config.prompts.knowledge import (
    KNOWLEDGE_UNCONFIGURED,
    TOPOLOGY_EMPTY,
    TOPOLOGY_TRUNCATED,
    TOPOLOGY_UNCONFIGURED,
)
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import capability_marker
from core.capability.result import CapabilityErrorClass
from platform.knowledge.base.models import Chunk, Citation, DocumentOrigin, DocumentType
from platform.knowledge.base.search import KnowledgeQuery, KnowledgeResult, RetrievedChunk
from platform.knowledge.errors import DocumentRejected
from platform.knowledge.proposals import KnowledgeProposal, ProposalState
from platform.knowledge.topology.models import (
    BlastRadius,
    DependencySet,
    ReachedService,
    ServiceNode,
)
from platform.knowledge.topology.queries import ServiceTopology

pytestmark = pytest.mark.unit

MOMENT = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

#: Staleness is judged against the real clock, because the capability stamps its
#: own answer — so a fixture that wants a *fresh* verification has to be fresh.
RECENT = datetime.now(UTC)


def service(node_id: str, *, verified: datetime | None = RECENT) -> ServiceNode:
    """Return one service node, verified just now unless told otherwise."""
    return ServiceNode(node_id=node_id, source="kubernetes", verified_at=verified)


def topology(*, truncated: bool = False, empty: bool = False) -> ServiceTopology:
    """Return one topology answer."""
    if empty:
        return ServiceTopology(
            service="checkout",
            depth=3,
            dependencies=DependencySet(origin="checkout", depth=3),
            dependents=DependencySet(origin="checkout"),
            blast_radius=BlastRadius(origin="checkout", max_depth=3),
        )
    return ServiceTopology(
        service="checkout",
        depth=3,
        dependencies=DependencySet(
            origin="checkout",
            services=(service("payments"), service("payments-db", verified=None)),
            depth=3,
        ),
        dependents=DependencySet(origin="checkout", services=(service("web"),)),
        blast_radius=BlastRadius(
            origin="checkout",
            max_depth=3,
            reaches=(ReachedService(service=service("web"), depth=1),),
            truncated=truncated,
        ),
    )


def passage() -> RetrievedChunk:
    """Return one retrieved passage with its citation."""
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id="payments-failover#0001",
            document_id="payments-failover",
            ordinal=1,
            text="Promote the standby, then drain the primary's connection pool.",
            section="Payments failover > Failing over",
        ),
        citation=Citation(
            document_id="payments-failover",
            title="Payments failover",
            section="Payments failover > Failing over",
            location="https://wiki.example/payments-failover",
            document_type=DocumentType.RUNBOOK,
            origin=DocumentOrigin.OPERATOR,
            updated_at=MOMENT,
        ),
        score=0.81,
    )


class StubTopology:
    """A topology source returning whatever the test told it to."""

    def __init__(self, answer: ServiceTopology) -> None:
        self.answer = answer
        self.calls: list[tuple[str, int]] = []

    async def query(self, service: str, *, depth: int = 3) -> ServiceTopology:
        """Record the question and return the fixed answer."""
        self.calls.append((service, depth))
        return self.answer


class StubKnowledge:
    """A knowledge source returning whatever the test told it to."""

    def __init__(self, result: KnowledgeResult) -> None:
        self.result = result
        self.queries: list[KnowledgeQuery] = []

    async def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Record the query and return the fixed result."""
        self.queries.append(query)
        return self.result


class StubQueue:
    """A review queue that records proposals and never applies one."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.proposals: list[KnowledgeProposal] = []

    async def propose(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        """Queue the proposal, or refuse it as the guardrail engine would."""
        if self.refuse:
            raise DocumentRejected(
                proposal.proposal_id,
                "the guardrail engine detected credential material in the proposed text",
            )
        self.proposals.append(proposal)
        return proposal


@pytest.fixture
def bound_topology() -> Iterator[StubTopology]:
    """Bind a topology source for the duration of one test."""
    source = StubTopology(topology())
    previous = topology_binding.bind(source)
    yield source
    topology_binding.restore(previous)


@pytest.fixture
def unbound_topology() -> Iterator[None]:
    """Leave topology unbound for the duration of one test."""
    previous = topology_binding.bind(None)
    yield
    topology_binding.restore(previous)


@pytest.fixture
def bound_knowledge() -> Iterator[StubKnowledge]:
    """Bind a knowledge source for the duration of one test."""
    source = StubKnowledge(
        KnowledgeResult(query=KnowledgeQuery(text="replica lag"), chunks=(passage(),))
    )
    previous = search_binding.bind(source)
    yield source
    search_binding.restore(previous)


@pytest.fixture
def bound_queue() -> Iterator[StubQueue]:
    """Bind a review queue for the duration of one test."""
    queue = StubQueue()
    previous = propose_binding.bind(queue)
    yield queue
    propose_binding.restore(previous)


# --- Declarations -------------------------------------------------------------


def test_the_two_read_capabilities_declare_themselves_as_reads() -> None:
    for declared in (query_service_topology, search_knowledge_base):
        marker = capability_marker(declared)
        assert marker is not None
        metadata = marker.metadata
        assert metadata.side_effect_level is SideEffectLevel.READ
        assert metadata.requires_approval is False
        assert metadata.parallel_safe is True
        assert metadata.use_cases and metadata.anti_examples


def test_the_proposal_capability_declares_a_write_that_needs_a_human() -> None:
    """FR-017 as a property of the declaration, not only of the queue."""
    marker = capability_marker(propose_knowledge)
    assert marker is not None
    metadata = marker.metadata

    assert metadata.side_effect_level is SideEffectLevel.WRITE_REVERSIBLE
    assert metadata.requires_approval is True
    assert metadata.approval_reason
    assert metadata.rollback_plan
    assert metadata.parallel_safe is False


def test_the_capabilities_declare_the_evidence_they_produce() -> None:
    kinds = {
        query_service_topology: EvidenceType.TOPOLOGY,
        search_knowledge_base: EvidenceType.DOCUMENT,
    }
    for declared, expected in kinds.items():
        marker = capability_marker(declared)
        assert marker is not None
        assert marker.metadata.evidence_type is expected


# --- Topology -----------------------------------------------------------------


async def test_topology_returns_both_directions_labelled_by_what_they_are_for(
    bound_topology: StubTopology,
) -> None:
    result = await query_service_topology("checkout")

    assert result.succeeded
    assert bound_topology.calls == [("checkout", 3)]
    assert [item["id"] for item in result.value["dependencies"]] == ["payments", "payments-db"]
    assert [item["id"] for item in result.value["dependents"]] == ["web"]
    assert topology_results.DEPENDENCY_RELATION in result.value["text"]
    assert topology_results.DEPENDENT_RELATION in result.value["text"]


async def test_an_unverified_dependency_is_marked_where_the_model_will_read_it(
    bound_topology: StubTopology,
) -> None:
    # Topology is a claim made at a moment by a source. The honest place for
    # "nobody has confirmed this" is beside the claim.
    result = await query_service_topology("checkout")

    unverified = [item for item in result.value["dependencies"] if item["unverified"]]
    assert [item["id"] for item in unverified] == ["payments-db"]
    assert "UNVERIFIED" in result.value["text"]


async def test_a_truncated_blast_radius_says_so_in_a_sentence() -> None:
    # An operator reading "one service affected" when the answer is "at least
    # one" has published a wrong incident update.
    source = StubTopology(topology(truncated=True))
    previous = topology_binding.bind(source)
    try:
        result = await query_service_topology("checkout")
    finally:
        topology_binding.restore(previous)

    assert result.truncated is True
    assert TOPOLOGY_TRUNCATED in result.value["text"]


async def test_an_empty_topology_answer_is_a_success_with_nothing_in_it() -> None:
    source = StubTopology(topology(empty=True))
    previous = topology_binding.bind(source)
    try:
        result = await query_service_topology("checkout")
    finally:
        topology_binding.restore(previous)

    assert result.succeeded
    assert result.value["text"] == TOPOLOGY_EMPTY.format(service="checkout")
    assert result.evidence == ()


async def test_an_unconfigured_graph_is_an_unavailability_not_an_empty_answer(
    unbound_topology: None,
) -> None:
    result = await query_service_topology("checkout")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert result.error.message == TOPOLOGY_UNCONFIGURED


async def test_a_degraded_traversal_is_an_unavailability_carrying_its_reason() -> None:
    degraded = ServiceTopology(
        service="checkout",
        depth=3,
        dependencies=DependencySet(origin="checkout", depth=3),
        dependents=DependencySet(origin="checkout"),
        blast_radius=BlastRadius(origin="checkout", max_depth=3),
        searched=False,
        reason="the graph extension is not installed",
    )
    previous = topology_binding.bind(StubTopology(degraded))
    try:
        result = await query_service_topology("checkout")
    finally:
        topology_binding.restore(previous)

    assert result.error is not None
    assert result.error.message == "the graph extension is not installed"


async def test_topology_evidence_says_it_records_rather_than_observes(
    bound_topology: StubTopology,
) -> None:
    # A conclusion citing this is citing what the graph records, not a
    # measurement of the running system.
    result = await query_service_topology("checkout")

    assert len(result.evidence) == 1
    assert "not an observation" in result.evidence[0].summary
    assert result.evidence[0].reference == "topology:checkout"


# --- Knowledge search ---------------------------------------------------------


async def test_a_passage_comes_back_with_everything_a_citation_needs(
    bound_knowledge: StubKnowledge,
) -> None:
    result = await search_knowledge_base("replica lag")

    assert result.succeeded
    found = result.value["passages"][0]
    assert found["title"] == "Payments failover"
    assert found["section"] == "Payments failover > Failing over"
    assert found["location"] == "https://wiki.example/payments-failover"
    assert found["reference"].startswith("https://wiki.example/payments-failover#")


async def test_knowledge_evidence_says_what_the_passage_is_not_what_it_asserts(
    bound_knowledge: StubKnowledge,
) -> None:
    result = await search_knowledge_base("replica lag")

    assert len(result.evidence) == 1
    assert "records what somebody wrote down" in result.evidence[0].summary
    assert result.evidence[0].evidence_type is EvidenceType.DOCUMENT


async def test_an_agent_originated_document_says_so_where_it_is_read() -> None:
    approved = passage()
    approved = RetrievedChunk(
        chunk=approved.chunk,
        citation=Citation(
            document_id=approved.citation.document_id,
            title=approved.citation.title,
            section=approved.citation.section,
            location=approved.citation.location,
            document_type=DocumentType.RUNBOOK,
            origin=DocumentOrigin.AGENT_PROPOSED,
            updated_at=MOMENT,
        ),
        score=0.9,
    )
    previous = search_binding.bind(
        StubKnowledge(KnowledgeResult(query=KnowledgeQuery(text="lag"), chunks=(approved,)))
    )
    try:
        result = await search_knowledge_base("lag")
    finally:
        search_binding.restore(previous)

    assert search_results.AGENT_ORIGIN_NOTE in result.value["text"]


async def test_an_unconfigured_knowledge_base_is_an_unavailability() -> None:
    previous = search_binding.bind(None)
    try:
        result = await search_knowledge_base("replica lag")
    finally:
        search_binding.restore(previous)

    assert result.error is not None
    assert result.error.message == KNOWLEDGE_UNCONFIGURED


async def test_an_empty_search_is_a_success_the_agent_can_act_on() -> None:
    previous = search_binding.bind(StubKnowledge(KnowledgeResult(query=KnowledgeQuery(text="lag"))))
    try:
        result = await search_knowledge_base("lag")
    finally:
        search_binding.restore(previous)

    assert result.succeeded
    assert result.value["count"] == 0
    assert "normal result" in result.value["text"]


# --- Proposals ----------------------------------------------------------------


async def test_a_proposal_receipt_says_outright_that_nothing_was_written(
    bound_queue: StubQueue,
) -> None:
    """SC-007 at the capability surface.

    An agent that believed its proposal had taken effect would cite it in the
    same investigation, and a citation to a document that does not exist is the
    failure Article I exists to prevent.
    """
    result = await propose_knowledge(
        title="Payments 5xx after a limit change",
        body="Compare the container memory limit against the previous revision.",
        correlation_id="corr-42",
    )

    assert result.succeeded
    assert result.value["applied"] is False
    assert result.value["state"] == ProposalState.PENDING.value
    assert "NOT part of the knowledge base" in result.value["text"]
    assert "Do not cite it" in result.value["text"]


async def test_a_proposal_produces_no_evidence(bound_queue: StubQueue) -> None:
    # An evidence entry for a proposal would put the agent's own suggestion into
    # the trace as a finding.
    result = await propose_knowledge(
        title="A thing", body="worth writing down", correlation_id="corr-42"
    )

    assert result.evidence == ()


async def test_a_proposal_carries_the_investigation_that_produced_it(
    bound_queue: StubQueue,
) -> None:
    await propose_knowledge(
        title="A thing",
        body="worth writing down",
        correlation_id="corr-42",
        rationale="three investigations ended here",
    )

    assert bound_queue.proposals[0].correlation_id == "corr-42"
    assert bound_queue.proposals[0].rationale == "three investigations ended here"


async def test_a_proposal_without_an_investigation_is_refused(
    bound_queue: StubQueue,
) -> None:
    result = await propose_knowledge(title="A thing", body="body", correlation_id="")

    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INVALID_ARGUMENTS
    assert bound_queue.proposals == []


async def test_a_proposal_carrying_a_secret_is_refused_without_quoting_it() -> None:
    queue = StubQueue(refuse=True)
    previous = propose_binding.bind(queue)
    try:
        result = await propose_knowledge(
            title="Recovery", body="use this key", correlation_id="corr-42"
        )
    finally:
        propose_binding.restore(previous)

    assert result.error is not None
    assert "credential material" in result.error.message
    assert "use this key" not in result.error.message


async def test_an_unconfigured_queue_does_not_pretend_to_have_queued_anything() -> None:
    previous = propose_binding.bind(None)
    try:
        result = await propose_knowledge(title="A thing", body="body", correlation_id="corr-42")
    finally:
        propose_binding.restore(previous)

    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
