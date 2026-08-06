"""Shared fixtures for the episodic memory suite.

Everything here is a real object rather than a mock. The gateway is the
in-memory persistence backend, which has real transactions and passes the same
contract suite as PostgreSQL; the embedder is the shipped local one; the
guardrail engine is the shipped default ruleset. The only doubles are the LLM
client — because extraction is one call and the point is what happens to its
*reply* — and a clock, so a recency assertion fails because ranking changed
rather than because the test ran at midnight.

Two teams and two organisations are created for every test, because "this team
cannot see that team's incidents" is something to assert rather than assume.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.llm.types import InvokeRequest, InvokeResult, StreamEvent, TokenEstimate
from platform.guardrails.engine import GuardrailEngine
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.extraction import EpisodeExtractor
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope

PRIMARY_ORG = "acme"
SECOND_ORG = "globex"

PAYMENTS_TEAM = "team-payments"
SEARCH_TEAM = "team-search"

#: A fixed instant, so a recency assertion fails because ranking changed rather
#: than because the suite ran at an awkward time of day.
EPOCH = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def at(days: float = 0.0) -> datetime:
    """Return the fixed instant offset by ``days``."""
    return EPOCH + timedelta(days=days)


@dataclass(slots=True)
class StubLLM:
    """An ``LLMClient`` that returns whatever a test told it to.

    ``raises`` is the interesting one: extraction has to survive a provider
    client that throws rather than degrades, and the only way to show that is to
    have one throw.
    """

    structured: Mapping[str, Any] | None = None
    raises: BaseException | None = None
    failure_message: str = ""
    calls: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Return the provider this stub claims to be."""
        return "stub"

    @property
    def model_id(self) -> str:
        """Return the model this stub claims to be."""
        return "stub-model"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return an empty successful result."""
        self.calls.append(request)
        return InvokeResult(provider_id=self.provider_id, model_id=self.model_id)

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Never used by extraction; present so this satisfies the port."""
        raise NotImplementedError("the memory suite does not stream")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the configured reply, or raise the configured exception."""
        self.calls.append(request)
        if self.raises is not None:
            raise self.raises
        if self.structured is None:
            from core.llm.failures import FailureClass

            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                partial=True,
                failure=FailureClass.TRANSIENT,
                failure_message=self.failure_message or "the provider was unavailable",
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=self.structured,
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a nominal estimate."""
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


#: A complete, well-formed extraction reply. Tests that care about one field
#: copy this and change that field, so a schema change breaks one place.
EXTRACTION_REPLY: dict[str, Any] = {
    "issue_type": "oom_kill",
    "issue_description": "payments-api pods restarting with exit code 137 since 03:04 UTC",
    "severity": "high",
    "components": [
        {"type": "service", "name": "payments-api"},
        {"type": "deployment", "name": "payments-api"},
    ],
    "key_findings": [
        {
            "capability": "describe_workload",
            "query": "payments-api",
            "finding": "last state OOMKilled, memory limit 512Mi",
        }
    ],
    "resolved": True,
    "root_cause": "the memory limit was lowered by the 02:50 deploy",
    "summary": (
        "payments-api began CrashLoopBackOff at 03:04 after a deploy lowered the "
        "container memory limit from 1Gi to 512Mi. Every restart is an OOMKill on "
        "the same container."
    ),
}


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with both organisations created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(PRIMARY_ORG, "Acme Corp")
        await system.orgs.create_organisation(SECOND_ORG, "Globex")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the team under test."""
    return TenantScope(org_id=PRIMARY_ORG, team_node_id=PAYMENTS_TEAM)


@pytest.fixture
def other_team_scope() -> TenantScope:
    """Return a second team in the same organisation."""
    return TenantScope(org_id=PRIMARY_ORG, team_node_id=SEARCH_TEAM)


@pytest.fixture
def other_org_scope() -> TenantScope:
    """Return a team in a different organisation."""
    return TenantScope(org_id=SECOND_ORG, team_node_id=PAYMENTS_TEAM)


@pytest.fixture
def embedder() -> LocalEmbedder:
    """Return the shipped local embedder."""
    return LocalEmbedder()


@pytest.fixture
def engine() -> GuardrailEngine:
    """Return the guardrail engine over the shipped ruleset."""
    return GuardrailEngine()


@pytest.fixture
def llm() -> StubLLM:
    """Return an LLM stub primed with a complete extraction reply."""
    return StubLLM(structured=dict(EXTRACTION_REPLY))


@pytest.fixture
def extractor(llm: StubLLM) -> EpisodeExtractor:
    """Return an extractor over the primed stub."""
    return EpisodeExtractor(llm=llm)
