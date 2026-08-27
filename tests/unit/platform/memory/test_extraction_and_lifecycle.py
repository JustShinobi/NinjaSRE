"""Writing the episode: exactly one, never twice, and never at the run's expense.

Four of the eight success criteria are asserted in this file.

**SC-001** — exactly one episode per conversation, verified with two turns
finishing at the same time. The race is real: ``asyncio.gather`` over two
finalisations of one session is precisely the interleaving a resumed run and a
late sub-agent produce, and it is the interleaving that would write two rows if
the claim came after an await.

**SC-006** — extraction failure never fails an investigation. Forced three ways:
a client that raises, a client that degrades, and a client that returns nothing
usable. All three leave the run untouched and record the reason.

**FR-006** — a result too short to be worth remembering is skipped and the skip
is recorded, so a deployment full of skips looks like one rather than like a team
that never has incidents.

**FR-024** — episode content passes the guardrail engine before persistence. The
episode is *redacted*, not dropped: the investigation already happened, the
secret is out of the text, and losing the corpus entry would lose the learning
for nothing.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.memory import MIN_EPISODE_RESULT_LENGTH
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.runtime_port import RunResult, RunStatus
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import ToolExecution, Turn
from core.capability.metadata import EvidenceType
from core.capability.telemetry import InvocationOutcome
from platform.guardrails.engine import GuardrailEngine
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.extraction import (
    EPISODE_EXTRACTION_SCHEMA,
    EpisodeExtractor,
    capability_sequence,
    observed_findings,
)
from platform.memory.lifecycle import MEMORY_LIFECYCLE_HOOK, MemoryLifecycle
from platform.memory.models import EpisodeSeverity, IssueType, MemoryEpisode
from platform.memory.policy import MemoryPolicy
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.memory.conftest import EXTRACTION_REPLY, PRIMARY_ORG, StubLLM

pytestmark = pytest.mark.unit

#: An answer long enough to be worth remembering, so a test about something else
#: is not accidentally a test about the length floor.
ANSWER = (
    "payments-api entered CrashLoopBackOff at 03:04 UTC. Every restart is an OOMKill "
    "on the api container, whose memory limit was lowered from 1Gi to 512Mi by the "
    "deploy at 02:50. The working set has not changed. Raising the limit back to 1Gi "
    "is expected to resolve it; the deploy that lowered it should be reviewed."
)


def session(
    *,
    session_id: str = "conv-1",
    parent_id: str = "",
    capabilities: tuple[str, ...] = ("describe_workload", "read_logs"),
    evidence: int = 4,
    cited: int = 3,
    iterations: int = 4,
) -> Session:
    """Return a finished session with a trace worth extracting from."""
    built = Session(
        id=session_id,
        objective="payments-api is CrashLoopBackOff",
        parent_id=parent_id,
        iteration=iterations,
        started_at=datetime(2026, 6, 1, 3, 4, tzinfo=UTC),
    )
    for index in range(evidence):
        built.record_evidence(
            EvidenceEntry(
                id=f"e{index + 1}",
                capability=capabilities[index % len(capabilities)],
                summary=f"observation {index + 1}",
                evidence_type=EvidenceType.LOG,
                source="kubernetes",
                reference=f"pod/payments-api-{index}",
                cited=index < cited,
            )
        )
    built.record_turn(
        Turn(
            index=1,
            executions=tuple(
                ToolExecution(
                    call_id=f"c{position}",
                    capability=name,
                    outcome=InvocationOutcome.SUCCESS,
                )
                for position, name in enumerate(capabilities)
            ),
        )
    )
    return built


def result(built: Session, answer: str = ANSWER) -> RunResult:
    """Return the run result the loop would have handed to ``on_run_end``."""
    return RunResult(session=built, status=RunStatus.COMPLETED, answer=answer)


def lifecycle(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    llm: StubLLM | None = None,
    policy: MemoryPolicy | None = None,
    engine: GuardrailEngine | None = None,
) -> MemoryLifecycle:
    """Return a lifecycle over the in-memory gateway and the local embedder."""
    return MemoryLifecycle(
        gateway=gateway,
        scope=scope,
        embedder=LocalEmbedder(),
        extractor=EpisodeExtractor(llm=llm or StubLLM(structured=dict(EXTRACTION_REPLY))),
        policy=policy or MemoryPolicy(),
        engine=engine,
        clock=lambda: datetime(2026, 6, 1, 3, 9, tzinfo=UTC),
    )


async def stored(gateway: PersistenceGateway, scope: TenantScope) -> tuple[MemoryEpisode, ...]:
    """Return every episode this team holds, as domain records."""
    async with gateway.begin(scope) as uow:
        rows = await uow.episodes.list_recent(limit=50)
    return tuple(MemoryEpisode.from_stored(row, org_id=scope.org_id) for row in rows)


# -- the trace ----------------------------------------------------------------


def test_the_capability_sequence_comes_from_the_trace_not_the_model() -> None:
    """FR-014's input is what happened, not what the model recalls happening."""
    assert capability_sequence(session()) == ("describe_workload", "read_logs")


def test_denied_and_replayed_calls_are_not_part_of_the_trajectory() -> None:
    """A trajectory that includes a refusal teaches the next run to repeat it."""
    built = session(capabilities=("read_logs",))
    built.record_turn(
        Turn(
            index=2,
            executions=(
                ToolExecution(call_id="d1", capability="restart_workload", denied=True),
                ToolExecution(call_id="r1", capability="read_logs", replayed=True),
                ToolExecution(call_id="s1", capability="deploy_history"),
            ),
        )
    )

    assert capability_sequence(built) == ("read_logs", "deploy_history")


def test_the_extraction_request_is_shown_the_runs_own_observations() -> None:
    """Evidence is what the system observed; the transcript is what the model said."""
    findings = observed_findings(session())

    assert findings[0].capability == "describe_workload"
    assert findings[0].query == "pod/payments-api-0"


# -- extraction ---------------------------------------------------------------


async def test_a_short_result_is_skipped_and_the_skip_is_recorded(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-006: below the floor there is no episode, and there is a reason."""
    short = "Nothing conclusive." * 2
    assert len(short) < MIN_EPISODE_RESULT_LENGTH

    outcome = await lifecycle(gateway, scope).finalise(session(), result(session(), short))

    assert outcome.skipped
    assert str(MIN_EPISODE_RESULT_LENGTH) in outcome.reason
    assert await stored(gateway, scope) == ()


@pytest.mark.parametrize(
    "llm",
    [
        StubLLM(raises=RuntimeError("the embedding service exploded")),
        StubLLM(structured=None, failure_message="the provider was unavailable"),
        StubLLM(structured={}),
    ],
    ids=["raised", "degraded", "empty_object"],
)
async def test_extraction_failure_never_fails_the_investigation(
    gateway: PersistenceGateway, scope: TenantScope, llm: StubLLM
) -> None:
    """SC-006, forced three ways. The run is untouched and the reason is recorded."""
    built = session()

    outcome = await lifecycle(gateway, scope, llm=llm).finalise(built, result(built))

    assert not outcome.written
    assert built.status.value == "running", "finalisation must not touch the run"


async def test_the_hook_swallows_a_store_that_is_not_there(
    gateway: PersistenceGateway,
) -> None:
    """A memory failure of any kind is a memory failure, never a failed run."""
    missing = TenantScope(org_id="no-such-org", team_node_id="team-payments")
    built = session()

    await lifecycle(gateway, missing).on_run_end(built, result(built))


async def test_a_reply_with_no_content_produces_no_episode(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """An episode with nothing in it costs a row, a vector, and a neighbour slot.

    It matches nothing, so it returns none of them. A structured reply that
    parsed cleanly and said nothing is a failure, not a very quiet episode.
    """
    built = session()

    outcome = await lifecycle(gateway, scope, llm=StubLLM(structured={})).finalise(
        built, result(built)
    )

    assert outcome.episode is None
    assert "neither an issue type nor a summary" in outcome.reason
    assert await stored(gateway, scope) == ()


# -- the controlled vocabulary ------------------------------------------------


def test_the_extraction_call_offers_the_model_the_closed_set() -> None:
    """The model picks from a list rather than inventing a label each time.

    A schema enum is where "both ends honour the vocabulary" is actually
    enforced on the writing end: a provider with native structured output will
    not emit a value outside it, and one without has still been shown the list.
    """
    issue_type = EPISODE_EXTRACTION_SCHEMA["properties"]["issue_type"]

    assert issue_type["enum"] == [member.value for member in IssueType]
    assert IssueType.OTHER.value in issue_type["enum"]


async def test_an_invented_issue_type_is_classified_and_its_words_are_kept(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A model that answers off the list costs its label, never its episode.

    The enum is a request, not a guarantee — most providers do not enforce one.
    So an unlisted answer is classified into the bucket it belongs to, and the
    words the model chose are stored beside it. A corpus that discarded what it
    could not classify would discard exactly the incident nobody has seen before.
    """
    reply = dict(EXTRACTION_REPLY) | {"issue_type": "ProxmoxGuestStopped"}
    built = session()

    outcome = await lifecycle(gateway, scope, llm=StubLLM(structured=reply)).finalise(
        built, result(built)
    )

    assert outcome.episode is not None
    assert outcome.episode.issue_type == IssueType.WORKLOAD_STOPPED.value
    assert outcome.episode.issue_label == "ProxmoxGuestStopped"


async def test_a_failure_nobody_can_classify_is_still_written(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """``other`` is a bucket, not a rejection.

    The label is what survives: an episode filed under ``other`` with the words
    ``ceph_pg_inconsistent`` on it is one a person can find and one the next
    extraction of the same failure will agree with.
    """
    reply = dict(EXTRACTION_REPLY) | {"issue_type": "ceph_pg_inconsistent_wibble"}
    built = session()

    outcome = await lifecycle(gateway, scope, llm=StubLLM(structured=reply)).finalise(
        built, result(built)
    )

    assert outcome.episode is not None
    assert outcome.episode.issue_type == IssueType.OTHER.value
    assert outcome.episode.issue_label == "ceph_pg_inconsistent_wibble"
    assert await stored(gateway, scope) != ()


async def test_a_reply_carrying_only_the_other_bucket_is_not_an_episode(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A closed vocabulary must not make an empty reply look like a classified one.

    Before the enum, "no issue type" was an empty string and clearly nothing.
    A model that answers the enum's own escape hatch and nothing else has said
    just as little, and writing that as an episode would put a row and a vector
    in the corpus for a run that classified nothing and summarised nothing.
    """
    built = session()

    outcome = await lifecycle(
        gateway, scope, llm=StubLLM(structured={"issue_type": "other"})
    ).finalise(built, result(built))

    assert outcome.episode is None
    assert await stored(gateway, scope) == ()


async def test_an_unusable_reply_says_which_keys_it_carried(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The reason has to be diagnosable from the log line alone.

    A live deployment recorded ``the structured reply named neither an issue type
    nor a summary`` and left nothing else behind, so the reply that produced it
    could not be told apart from an empty object, a wrapper of the wrong shape,
    or a truncation repaired into a document missing both fields. Naming the keys
    that did arrive separates all three without storing the reply itself.
    """
    built = session()

    outcome = await lifecycle(
        gateway, scope, llm=StubLLM(structured={"severity": "high", "resolved": True})
    ).finalise(built, result(built))

    assert outcome.episode is None
    assert "resolved" in outcome.reason
    assert "severity" in outcome.reason


# -- exactly once -------------------------------------------------------------


async def test_one_conversation_produces_exactly_one_episode(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001, the ordinary case."""
    built = session()

    outcome = await lifecycle(gateway, scope).finalise(built, result(built))

    episodes = await stored(gateway, scope)
    assert outcome.written
    assert len(episodes) == 1
    assert episodes[0].correlation_id == "conv-1"
    assert episodes[0].run_id == "conv-1"


async def test_two_turns_finishing_at_once_still_produce_one_episode(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001 under the race the requirement actually names.

    The claim on the correlation id happens before the first await, so the
    second coroutine finds the conversation already claimed. Without that, both
    would reach extraction and both would write.
    """
    built = session()
    hook = lifecycle(gateway, scope)

    outcomes = await asyncio.gather(
        hook.finalise(built, result(built)),
        hook.finalise(built, result(built)),
    )

    assert len(await stored(gateway, scope)) == 1
    assert sum(1 for outcome in outcomes if outcome.written) == 1
    assert sum(1 for outcome in outcomes if outcome.skipped) == 1


async def test_a_second_turn_updates_the_episode_and_keeps_both_trajectories(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Acceptance scenario 2, plus the capability merge that makes it worth doing."""
    first = session(capabilities=("describe_workload", "read_logs"))
    await lifecycle(gateway, scope).finalise(first, result(first))

    second = session(capabilities=("read_logs", "deploy_history"))
    await lifecycle(gateway, scope).finalise(second, result(second))

    episodes = await stored(gateway, scope)
    assert len(episodes) == 1
    assert episodes[0].capabilities_used == (
        "describe_workload",
        "read_logs",
        "deploy_history",
    )


async def test_a_subagents_session_belongs_to_its_parents_episode(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A five-specialist investigation is one conversation, not six."""
    child = session(session_id="sub-1", parent_id="conv-1")

    await lifecycle(gateway, scope).finalise(child, result(child))

    episodes = await stored(gateway, scope)
    assert [episode.correlation_id for episode in episodes] == ["conv-1"]


# -- what is written ----------------------------------------------------------


async def test_the_episode_records_everything_the_requirement_names(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Acceptance scenario 7, field by field."""
    built = session()

    outcome = await lifecycle(gateway, scope).finalise(built, result(built))
    episode = outcome.episode
    assert episode is not None

    assert episode.issue_type == "oom_kill"
    assert episode.severity is EpisodeSeverity.HIGH
    assert [component.name for component in episode.components] == [
        "payments-api",
        "payments-api",
    ]
    assert episode.capabilities_used == ("describe_workload", "read_logs")
    assert episode.key_findings[0].capability == "describe_workload"
    assert episode.resolved is True
    assert episode.root_cause.startswith("the memory limit")
    assert 0.0 < episode.effectiveness_score <= 1.0
    assert episode.duration_seconds == pytest.approx(timedelta(minutes=5).total_seconds())
    assert episode.org_id == PRIMARY_ORG
    assert episode.team_node_id == scope.team_node_id
    assert episode.embedding_model == LocalEmbedder().model


async def test_the_vector_lands_beside_the_episode_in_one_unit_of_work(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A vector pointing at nothing is worse than no vector at all."""
    built = session()

    await lifecycle(gateway, scope).finalise(built, result(built))

    from config.constants.persistence import EPISODE_VECTOR_NAMESPACE

    async with gateway.begin(scope) as uow:
        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 1


async def test_episode_content_is_scanned_before_it_is_persisted(
    gateway: PersistenceGateway, scope: TenantScope, engine: GuardrailEngine
) -> None:
    """FR-024: a secret in an episode is a secret in every backup from then on.

    Redacted rather than dropped. The investigation already happened; discarding
    the record would lose the learning and the secret is already out of the text.
    """
    leaking = dict(EXTRACTION_REPLY)
    leaking["summary"] = (
        "The deploy set password=hunter2correcthorse in the manifest, and the pod could not start."
    )
    built = session()

    outcome = await lifecycle(
        gateway, scope, llm=StubLLM(structured=leaking), engine=engine
    ).finalise(built, result(built))

    episode = outcome.episode
    assert episode is not None
    assert "hunter2correcthorse" not in episode.summary
    assert episode.guardrail_rules_fired, "the rules that fired are recorded on the episode"

    async with gateway.begin(scope) as uow:
        rows = await uow.episodes.list_recent(limit=5)
    assert "hunter2correcthorse" not in rows[0].summary


# -- ablation -----------------------------------------------------------------


async def test_writing_disabled_writes_nothing_and_says_so(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """FR-020: the write half of the ablation switch."""
    built = session()
    policy = MemoryPolicy().without("memory_write")

    outcome = await lifecycle(gateway, scope, policy=policy).finalise(built, result(built))

    assert outcome.skipped
    assert await stored(gateway, scope) == ()


def test_the_finalisation_hook_attaches_where_the_loop_dispatches_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """``on_run_end`` runs whichever way the run ended, which is why it is that point."""
    hooks = HookRegistry()
    lifecycle(gateway, scope).register(hooks)

    assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_END)] == [MEMORY_LIFECYCLE_HOOK]


def test_an_episode_cannot_be_written_without_a_team(gateway: PersistenceGateway) -> None:
    """FR-023 is enforced at construction, not at the write."""
    with pytest.raises(ValueError, match="under a team"):
        MemoryLifecycle(
            gateway=gateway,
            scope=TenantScope(org_id=PRIMARY_ORG),
            embedder=LocalEmbedder(),
            extractor=EpisodeExtractor(llm=StubLLM()),
        )
