"""The prompt stays clean, and the two switches switch independently.

**FR-020** is asserted by populating both stores and *then* looking at the
opening prompt. It is not enough to check that the guidance paragraphs contain no
service names: the requirement is that nothing about the estate or the team's
documentation reaches the prompt, and the way to show that is to put something
distinctive in each store first.

**SC-008** is the ablation identity, twice. Each store has to be disablable on
its own, leaving the other exactly as it was — and "disabled" has to mean the
guidance paragraph is absent and the retrieval path is unreachable, not that a
hook runs and returns early. A baseline that differs from the real thing by one
extra no-op hook is not a baseline.
"""

from __future__ import annotations

import pytest

from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from config.prompts.knowledge import (
    KNOWLEDGE_DISABLED,
    KNOWLEDGE_GUIDANCE,
    TOPOLOGY_DISABLED,
    TOPOLOGY_GUIDANCE,
)
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.models import Document, DocumentType
from platform.knowledge.base.search import KnowledgeQuery
from platform.knowledge.guidance import KNOWLEDGE_GUIDANCE_HOOK
from platform.knowledge.policy import (
    KNOWLEDGE_SWITCH,
    KNOWLEDGE_SWITCHES,
    TOPOLOGY_SWITCH,
    KnowledgePolicy,
)
from platform.knowledge.service import KnowledgeService
from platform.knowledge.topology.models import DependencyEdge, DependencyKind
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import PAYMENTS_TEAM, PRIMARY_ORG, Clock

pytestmark = pytest.mark.unit

#: Distinctive strings from each store. If either reaches the opening prompt, the
#: store was pre-injected.
TOPOLOGY_PHRASE = "ledger-writer"
KNOWLEDGE_PHRASE = "drain the primary's connection pool"

RUNBOOK = f"""# Payments failover

## Failing over

Promote the standby, then {KNOWLEDGE_PHRASE} before restarting.
"""


def run_session() -> Session:
    """Return a session as the runtime would have built it."""
    return Session(
        id="conv-1",
        objective="checkout is returning 502s",
        system_prompt=DEFAULT_RUNTIME_SYSTEM_PROMPT,
    )


def service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    clock: Clock,
    *,
    policy: KnowledgePolicy | None = None,
) -> KnowledgeService:
    """Return a wired knowledge service over the in-memory gateway."""
    return KnowledgeService(
        gateway=gateway,
        scope=scope,
        embedder=LocalEmbedder(),
        policy=policy,
        engine=GuardrailEngine(),
        clock=clock,
    )


async def populate(store: KnowledgeService) -> None:
    """Put something distinctive in both stores."""
    await store.writer.upsert_dependency(
        DependencyEdge(
            from_node_id="checkout", to_node_id=TOPOLOGY_PHRASE, kind=DependencyKind.CALLS
        )
    )
    await store.ingestor.ingest(
        Document(
            document_id="payments-failover",
            org_id=PRIMARY_ORG,
            team_node_id=PAYMENTS_TEAM,
            title="Payments failover",
            body=RUNBOOK,
            document_type=DocumentType.RUNBOOK,
        )
    )


# -- the prompt ---------------------------------------------------------------


async def test_the_opening_prompt_carries_guidance_and_no_content_from_either_store(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """FR-020 and FR-021, asserted against populated stores."""
    store = service(gateway, scope, clock)
    await populate(store)
    session = run_session()

    await store.guidance.on_run_start(session)

    assert TOPOLOGY_GUIDANCE in session.system_prompt
    assert KNOWLEDGE_GUIDANCE in session.system_prompt
    assert TOPOLOGY_PHRASE not in session.system_prompt
    assert KNOWLEDGE_PHRASE not in session.system_prompt


async def test_the_guidance_is_appended_once(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # A resumed session already carries what its first start appended, and a
    # resumed run whose prompt differs from a fresh one is not comparable with it.
    store = service(gateway, scope, clock)
    session = run_session()

    await store.guidance.on_run_start(session)
    await store.guidance.on_run_start(session)

    assert session.system_prompt.count(TOPOLOGY_GUIDANCE) == 1
    assert session.system_prompt.count(KNOWLEDGE_GUIDANCE) == 1


async def test_the_guidance_is_appended_after_the_prompt_it_was_given(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    store = service(gateway, scope, clock)
    session = run_session()

    await store.guidance.on_run_start(session)

    assert session.system_prompt.startswith(DEFAULT_RUNTIME_SYSTEM_PROMPT)


# -- the switches -------------------------------------------------------------


async def test_disabling_topology_removes_its_paragraph_and_leaves_the_other(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """SC-008, first axis."""
    store = service(gateway, scope, clock, policy=KnowledgePolicy(topology_enabled=False))
    session = run_session()

    await store.guidance.on_run_start(session)

    assert TOPOLOGY_GUIDANCE not in session.system_prompt
    assert KNOWLEDGE_GUIDANCE in session.system_prompt


async def test_disabling_the_knowledge_base_removes_its_paragraph_and_leaves_the_other(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """SC-008, second axis."""
    store = service(gateway, scope, clock, policy=KnowledgePolicy(knowledge_enabled=False))
    session = run_session()

    await store.guidance.on_run_start(session)

    assert KNOWLEDGE_GUIDANCE not in session.system_prompt
    assert TOPOLOGY_GUIDANCE in session.system_prompt


async def test_a_disabled_store_is_unreachable_not_merely_unmentioned(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # The paragraph and the path switch together. A run told not to query a graph
    # that would still answer is a run whose ablation measured nothing.
    populated = service(gateway, scope, clock)
    await populate(populated)

    ablated = service(gateway, scope, clock, policy=KnowledgePolicy.disabled())
    answer = await ablated.topology.query("checkout")
    result = await ablated.search.search(KnowledgeQuery(text="drain the pool"))

    assert answer.searched is False
    assert answer.reason == TOPOLOGY_DISABLED
    assert result.searched is False
    assert result.reason == KNOWLEDGE_DISABLED


async def test_both_switches_off_registers_no_hook_at_all(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """ "Off" is the code path a deployment without either store takes."""
    hooks = HookRegistry()
    service(gateway, scope, clock, policy=KnowledgePolicy.disabled()).install(hooks)

    assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_START)] == []


async def test_either_switch_on_registers_exactly_one_hook(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    for policy in (
        KnowledgePolicy(topology_enabled=False),
        KnowledgePolicy(knowledge_enabled=False),
        KnowledgePolicy(),
    ):
        hooks = HookRegistry()
        service(gateway, scope, clock, policy=policy).install(hooks)

        assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_START)] == [
            KNOWLEDGE_GUIDANCE_HOOK
        ]


def test_the_switches_are_the_axes_the_harness_enumerates() -> None:
    assert set(KNOWLEDGE_SWITCHES) == {TOPOLOGY_SWITCH, KNOWLEDGE_SWITCH}

    both_off = KnowledgePolicy().without(*KNOWLEDGE_SWITCHES)
    assert both_off.enabled is False

    one_off = KnowledgePolicy().without(TOPOLOGY_SWITCH)
    assert one_off.topology_enabled is False
    assert one_off.knowledge_enabled is True


def test_an_unknown_ablation_axis_is_refused() -> None:
    # A table saying it measured something it never varied is worse than no
    # table at all.
    with pytest.raises(ValueError, match="unknown knowledge switch"):
        KnowledgePolicy().without("topolgy")


def test_a_policy_is_frozen_so_an_ablation_cannot_leak_into_the_next_run() -> None:
    policy = KnowledgePolicy()

    ablated = policy.without(TOPOLOGY_SWITCH)

    assert policy.topology_enabled is True
    assert ablated is not policy


async def test_the_trace_separates_configuration_from_what_happened(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """ "Topology was off" and "topology held nothing" are different facts."""
    store = service(gateway, scope, clock)
    await populate(store)
    await store.topology.query("checkout")
    await store.search.search(KnowledgeQuery(text="drain the pool"))

    summary = store.trace_summary()

    assert summary["topology_enabled"] is True
    assert summary["knowledge_enabled"] is True
    assert summary["topology_queries"] == 1
    assert summary["knowledge_searches"] == 1
    assert summary["topology_degradations"] == 0
