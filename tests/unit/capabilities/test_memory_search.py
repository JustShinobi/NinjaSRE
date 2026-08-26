"""The recall capability: its declaration, its three outcomes, and what it shows.

The declaration is checked against the catalogue's rules because those rules are
what the scorer, the approval gate, and the console read — a tool that reaches
the catalogue having promised nothing is worse than one that is absent, because
it will be selected.

The three outcomes are checked because they are three on purpose. Episodes are a
lead. An empty search is a finding — this failure is new to the team. An
unavailability is not a finding at all, and collapsing it into an empty search
would teach the agent that a team with no configured memory has no history.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from capabilities.tools.system.memory_search import binding, results
from capabilities.tools.system.memory_search.tool import TOOL_NAME, recall_similar_incidents
from config.constants.memory import DEFAULT_MEMORY_RECALL_RESULTS
from core.capability.metadata import EvidenceSource, EvidenceType, SideEffectLevel
from core.capability.registered import capability_marker
from core.capability.result import CapabilityErrorClass
from platform.memory.models import (
    Component,
    MemoryEpisode,
    RecallQuery,
    ScoredEpisode,
)
from platform.memory.retrieval import RecallResult

pytestmark = pytest.mark.unit


def episode(correlation_id: str = "conv-42", *, resolved: bool = True) -> MemoryEpisode:
    """Return one recalled episode."""
    return MemoryEpisode(
        correlation_id=correlation_id,
        org_id="acme",
        team_node_id="team-payments",
        issue_type="oom_kill",
        issue_description="payments-api restarting with exit code 137",
        components=(Component(type="service", name="payments-api"),),
        capabilities_used=("describe_workload", "read_logs", "deploy_history"),
        resolved=resolved,
        root_cause="the 02:50 deploy lowered the container memory limit",
        summary="Every restart is an OOMKill on the api container.",
        effectiveness_score=0.87,
    )


class StubRecall:
    """A recall source that returns whatever the test told it to."""

    def __init__(self, result: RecallResult) -> None:
        self.result = result
        self.queries: list[RecallQuery] = []

    async def search(self, query: RecallQuery) -> RecallResult:
        """Record the query and return the configured result."""
        self.queries.append(query)
        return self.result


@pytest.fixture(autouse=True)
def unbound() -> Iterator[None]:
    """Leave the binding exactly as it was found, whatever a test did to it."""
    previous = binding.current()
    yield
    binding.restore(previous)


def bind(result: RecallResult) -> StubRecall:
    """Bind a stub recall source and return it."""
    source = StubRecall(result)
    binding.bind(source)
    return source


def found(*episodes: MemoryEpisode) -> RecallResult:
    """Return a successful recall over ``episodes``."""
    return RecallResult(
        query=RecallQuery(text="exit code 137"),
        episodes=tuple(ScoredEpisode(episode=item, similarity=0.9, score=0.8) for item in episodes),
    )


# -- the declaration ----------------------------------------------------------


def test_the_declaration_is_complete_and_read_only() -> None:
    """Article IX: what the scorer, the gate, and the console read."""
    registered = capability_marker(recall_similar_incidents)
    assert registered is not None

    metadata = registered.metadata
    assert metadata.name == TOOL_NAME
    assert metadata.evidence_source == EvidenceSource.MEMORY
    assert metadata.evidence_type is EvidenceType.INCIDENT
    assert metadata.side_effect_level is SideEffectLevel.READ
    assert metadata.parallel_safe
    assert not metadata.requires_approval
    assert metadata.use_cases and metadata.anti_examples


def test_the_declaration_takes_a_query_and_the_two_optional_filters() -> None:
    """FR-011, as the model sees it."""
    registered = capability_marker(recall_similar_incidents)
    assert registered is not None

    properties = registered.input_schema["properties"]
    assert set(properties) == {"query", "component", "issue_type", "limit"}
    assert registered.input_schema["required"] == ["query"]


def test_the_description_tells_the_agent_when_to_search() -> None:
    """FR-010's other half: the anti-example is where the design decision lives."""
    registered = capability_marker(recall_similar_incidents)
    assert registered is not None

    assert "before any evidence has been gathered" in " ".join(registered.metadata.anti_examples)


# -- the three outcomes -------------------------------------------------------


async def test_an_unconfigured_deployment_says_so_rather_than_returning_nothing() -> None:
    """ "Nowhere to look" must never look like "nothing found"."""
    binding.clear()

    result = await recall_similar_incidents(query="exit code 137")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert "not configured" in result.error.message


async def test_a_search_that_did_not_run_is_an_unavailability() -> None:
    """An operator's ablation switch is not a statement about the corpus."""
    bind(
        RecallResult(
            query=RecallQuery(text="exit code 137"),
            searched=False,
            reason="Episodic memory recall is switched off for this team.",
        )
    )

    result = await recall_similar_incidents(query="exit code 137")

    assert not result.succeeded
    assert result.error is not None
    assert "switched off" in result.error.message


async def test_an_empty_search_is_a_successful_finding() -> None:
    """FR-015: this failure is new to the team, which is worth knowing."""
    bind(RecallResult(query=RecallQuery(text="exit code 137")))

    result = await recall_similar_incidents(query="exit code 137")

    assert result.succeeded
    assert result.value["count"] == 0
    assert "normal result" in result.value["text"]
    assert result.evidence == ()


async def test_a_real_retriever_over_an_empty_corpus_still_searched() -> None:
    """The two "nothings", told apart over the store rather than over a stub.

    This is what a freshly composed deployment actually hits: a team that has
    never written an episode has no vector namespace at all. The stub above
    proves the tool renders an empty result; this proves that the retriever a
    composition root binds *produces* one, rather than reporting that there was
    nowhere to look — which is the answer every deployment's first weeks would
    otherwise give, and is indistinguishable from memory never having been
    configured.
    """
    from platform.memory.embeddings.local import LocalEmbedder
    from platform.memory.retrieval import MemoryRetriever
    from platform.persistence.fakes import FakePersistence
    from platform.persistence.ports.transaction import TenantScope

    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    binding.bind(
        MemoryRetriever(
            gateway=store,
            scope=TenantScope(org_id="acme", team_node_id="team-payments"),
            embedder=LocalEmbedder(),
        )
    )

    searched = await recall_similar_incidents(query="exit code 137")
    binding.clear()
    unconfigured = await recall_similar_incidents(query="exit code 137")

    assert searched.succeeded and searched.value["count"] == 0
    assert not unconfigured.succeeded
    assert unconfigured.error is not None
    assert unconfigured.error.classification is CapabilityErrorClass.UNAVAILABLE


async def test_a_match_comes_back_with_its_trajectory_and_its_evidence() -> None:
    """FR-014: the capability sequence is what makes recall cheaper than rediscovery."""
    bind(found(episode()))

    result = await recall_similar_incidents(query="exit code 137")

    assert result.succeeded
    assert result.value["count"] == 1
    assert result.value["episodes"][0]["capabilities_used"] == [
        "describe_workload",
        "read_logs",
        "deploy_history",
    ]
    assert "describe_workload, read_logs, deploy_history" in result.value["text"]
    assert result.evidence[0].reference == "episode:conv-42"


async def test_the_filters_reach_the_retriever() -> None:
    """A filter the tool dropped would silently widen every search."""
    source = bind(found(episode()))

    await recall_similar_incidents(
        query="exit code 137", component="payments-api", issue_type="oom_kill", limit=3
    )

    assert source.queries[0].component == "payments-api"
    assert source.queries[0].issue_type == "oom_kill"
    assert source.queries[0].limit == 3


async def test_the_default_limit_is_the_constant_not_a_literal() -> None:
    """Article II: a bound at a call site is a defect, not a style preference."""
    source = bind(found(episode()))

    await recall_similar_incidents(query="exit code 137")

    assert source.queries[0].limit == DEFAULT_MEMORY_RECALL_RESULTS


# -- what the model is shown --------------------------------------------------


def test_every_rendered_episode_says_what_resolved_means() -> None:
    """FR-003 surfaces here too, and this is where an agent would misread it."""
    rendered = results.render(found(episode(resolved=True), episode("conv-43", resolved=False)))

    assert results.OUTCOME_RESOLVED in rendered
    assert results.OUTCOME_UNRESOLVED in rendered
    assert "fixed" not in rendered


def test_the_shaped_result_carries_both_the_text_and_the_structure() -> None:
    """The model reads one, the trace and the harness read the other."""
    shaped = results.shape(found(episode()))

    assert shaped["text"]
    assert shaped["episodes"][0]["correlation_id"] == "conv-42"
    assert set(shaped["episodes"][0]["ranking_terms"]) == {
        "similarity",
        "resolved",
        "component_overlap",
        "effectiveness",
        "recency",
    }


def test_recalled_evidence_is_the_episode_rather_than_its_findings() -> None:
    """A past finding presented as an observation of this run is a fabricated citation."""
    evidence = results.evidence_for(found(episode()).episodes)

    assert evidence[0].source == EvidenceSource.MEMORY
    assert "A previous investigation" in evidence[0].summary
    assert evidence[0].reference.startswith(results.EPISODE_REFERENCE_PREFIX)


def test_binding_returns_what_it_replaced() -> None:
    """A caller that wants to scope a binding around one run can put the old one back."""
    first = StubRecall(found())
    second = StubRecall(found())

    binding.bind(first)
    replaced = binding.bind(second)

    assert replaced is first
    assert binding.current() is second
