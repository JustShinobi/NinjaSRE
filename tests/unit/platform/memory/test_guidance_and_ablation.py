"""The prompt stays clean, and the switches actually switch.

**SC-002** is asserted by inspecting the prompt after ``on_run_start``, against a
store that has episodes in it. It is not enough to check that the guidance
paragraph contains no episode text: the requirement is that *nothing* about a
past incident reaches the opening prompt, and the way to show that is to
populate memory first and then look at what the agent was given.

**SC-004** is the ablation identity. With memory disabled the run has to be
otherwise unchanged — same prompt, same hooks, same dispatch order — because a
baseline that differs from the real thing by two extra no-op hooks is not a
baseline. That is why disabling registers nothing rather than registering
something inert.
"""

from __future__ import annotations

import pytest

from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from config.prompts.memory import MEMORY_RECALL_GUIDANCE
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import Session
from platform.memory.guidance import MEMORY_GUIDANCE_HOOK, MemoryGuidance
from platform.memory.lifecycle import MEMORY_LIFECYCLE_HOOK
from platform.memory.models import MemoryEpisode, RecallQuery
from platform.memory.policy import (
    MEMORY_READ_SWITCH,
    MEMORY_SWITCHES,
    MEMORY_WRITE_SWITCH,
    MemoryPolicy,
)
from platform.memory.service import MemoryService
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.memory.conftest import StubLLM
from tests.unit.platform.memory.test_retrieval_and_ranking import episode, seed

pytestmark = pytest.mark.unit

#: A secret-free but highly distinctive phrase from the seeded corpus. If any of
#: it reaches the opening prompt, memory was pre-injected.
CORPUS_PHRASE = "the memory limit was lowered"


def run_session() -> Session:
    """Return a session as the runtime would have built it."""
    return Session(
        id="conv-1",
        objective="payments-api is CrashLoopBackOff",
        system_prompt=DEFAULT_RUNTIME_SYSTEM_PROMPT,
    )


def service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    policy: MemoryPolicy | None = None,
) -> MemoryService:
    """Return a wired memory service over the in-memory gateway."""
    return MemoryService(gateway=gateway, scope=scope, llm=StubLLM(), policy=policy)


# -- the prompt ---------------------------------------------------------------


async def test_the_opening_prompt_carries_guidance_and_no_episode_content(
    gateway: PersistenceGateway, scope: TenantScope, embedder: object
) -> None:
    """SC-002, asserted against a populated corpus rather than an empty one.

    An assertion that the guidance text contains no episode content would pass
    trivially. What has to be true is that the *prompt the agent receives*
    contains none, with episodes sitting in the store the whole time.
    """
    from platform.memory.embeddings.local import LocalEmbedder

    local = LocalEmbedder()
    await seed(gateway, scope, local, episode("oom", scope), episode("certs", scope))

    session = run_session()
    hooks = HookRegistry()
    service(gateway, scope).install(hooks)
    await hooks.run_run_start(session)

    assert MEMORY_RECALL_GUIDANCE in session.system_prompt
    assert DEFAULT_RUNTIME_SYSTEM_PROMPT in session.system_prompt
    assert CORPUS_PHRASE not in session.system_prompt
    assert "oom" not in session.system_prompt.replace("OOMKill", "")


def test_the_guidance_itself_names_no_incident() -> None:
    """The text is guidance about *when* to search, never about what was found."""
    assert "only once you hold" in MEMORY_RECALL_GUIDANCE
    assert "concrete evidence" in MEMORY_RECALL_GUIDANCE
    assert "empty result" in MEMORY_RECALL_GUIDANCE


async def test_guidance_is_appended_once_however_often_the_run_starts() -> None:
    """A resumed run must not accumulate the paragraph, or drift from a fresh one."""
    guidance = MemoryGuidance()
    session = run_session()

    await guidance.on_run_start(session)
    await guidance.on_run_start(session)

    assert session.system_prompt.count(MEMORY_RECALL_GUIDANCE) == 1


async def test_guidance_is_appended_rather_than_prepended() -> None:
    """The caller's framing is what the investigation is about; memory is an aside."""
    session = run_session()

    await MemoryGuidance().on_run_start(session)

    assert session.system_prompt.startswith(DEFAULT_RUNTIME_SYSTEM_PROMPT)


# -- the switches -------------------------------------------------------------


def test_the_two_switches_are_the_declared_ablation_axes() -> None:
    """The harness enumerates these; an axis that is not here cannot be varied."""
    assert MEMORY_SWITCHES == (MEMORY_READ_SWITCH, MEMORY_WRITE_SWITCH)


def test_switching_one_off_leaves_the_other_alone() -> None:
    """The interesting ablation is a populated corpus the agent may not consult."""
    read_off = MemoryPolicy().without(MEMORY_READ_SWITCH)

    assert not read_off.read_enabled
    assert read_off.write_enabled


def test_an_unknown_switch_is_refused() -> None:
    """A table saying it measured an axis it never varied is worse than no table."""
    with pytest.raises(ValueError, match="unknown memory switch"):
        MemoryPolicy().without("memory_everything")


def test_a_policy_is_frozen_so_an_ablation_cannot_leak_into_the_next_run() -> None:
    """``without`` returns a new policy; the original is untouched."""
    original = MemoryPolicy()

    original.without(MEMORY_READ_SWITCH, MEMORY_WRITE_SWITCH)

    assert original.read_enabled and original.write_enabled


def test_the_environment_reads_a_missing_value_as_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory is on unless an operator turned it off, including on a typo."""
    from config.constants.memory import NINJASRE_MEMORY_READ_ENV, NINJASRE_MEMORY_WRITE_ENV

    monkeypatch.delenv(NINJASRE_MEMORY_READ_ENV, raising=False)
    monkeypatch.setenv(NINJASRE_MEMORY_WRITE_ENV, "flase")

    policy = MemoryPolicy.from_environment()

    assert policy.read_enabled
    assert policy.write_enabled, "a mis-spelled value must not silently disable memory"


def test_the_environment_switch_turns_memory_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """And a value that reads as off does turn it off."""
    from config.constants.memory import NINJASRE_MEMORY_READ_ENV

    monkeypatch.setenv(NINJASRE_MEMORY_READ_ENV, "off")

    assert not MemoryPolicy.from_environment().read_enabled


# -- the identity SC-004 asks for ---------------------------------------------


def test_memory_disabled_installs_no_hooks_at_all(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-004: the baseline is the code path a deployment without memory takes.

    Not a no-op hook. A registered hook still dispatches, still appears in the
    trace, and still occupies a slot in the ordering a trajectory comparison
    reads — which would make the "identical" run measurably different.
    """
    hooks = HookRegistry()

    service(gateway, scope, policy=MemoryPolicy.disabled()).install(hooks)

    assert hooks.hooks_at(HookPoint.ON_RUN_START) == ()
    assert hooks.hooks_at(HookPoint.ON_RUN_END) == ()


def test_memory_enabled_installs_exactly_the_two_hooks(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Both halves, each registered under a name an ablation can find again."""
    hooks = HookRegistry()

    service(gateway, scope).install(hooks)

    assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_START)] == [MEMORY_GUIDANCE_HOOK]
    assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_END)] == [MEMORY_LIFECYCLE_HOOK]


async def test_a_disabled_run_leaves_the_prompt_exactly_as_it_was(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-004, at the prompt: the baseline's opening prompt is byte-identical."""
    baseline = run_session()
    ablated = run_session()

    hooks = HookRegistry()
    service(gateway, scope, policy=MemoryPolicy.disabled()).install(hooks)
    await hooks.run_run_start(ablated)

    assert ablated.system_prompt == baseline.system_prompt


async def test_a_disabled_run_neither_reads_nor_writes(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """And nothing reaches the store from either direction."""
    from platform.memory.embeddings.local import LocalEmbedder

    await seed(gateway, scope, LocalEmbedder(), episode("oom", scope))
    disabled = service(gateway, scope, policy=MemoryPolicy.disabled())

    found = await disabled.retriever.search(RecallQuery(text="payments-api exit code 137"))

    assert not found.searched
    assert found.empty


# -- what the trace says ------------------------------------------------------


def test_the_trace_separates_how_memory_was_configured_from_what_it_did(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """ "Recall was off" and "recall found nothing" have to be distinguishable."""
    summary = service(gateway, scope, policy=MemoryPolicy().without(MEMORY_READ_SWITCH))
    recorded = summary.trace_summary()

    assert recorded["memory_read_enabled"] is False
    assert recorded["memory_write_enabled"] is True
    assert recorded["recalls"] == 0


def test_the_service_shares_one_ledger_between_recall_and_finalisation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Both halves of FR-022 only work if they look at the same object."""
    wired = service(gateway, scope)

    assert wired.retriever.ledger is wired.lifecycle.ledger is wired.ledger


def test_an_episode_written_under_one_team_is_stamped_with_it(scope: TenantScope) -> None:
    """Guards the field the whole isolation story rests on."""
    assert (
        MemoryEpisode(
            correlation_id="c", org_id=scope.org_id, team_node_id=scope.team_node_id or ""
        ).team_node_id
        == scope.team_node_id
    )
