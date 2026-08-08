"""What has worked here before, where the decision can see it, and in memory.

Three requirements meet in this file. FR-014 wants the history queryable by
resource, capability and condition; FR-015 wants it in front of the proposing
agent and the human reviewer; FR-016 wants the learning to feed the episodic
memory the platform already has rather than a store of its own.

The one that is easiest to get subtly wrong is "never verified". A capability
whose three attempts are all still settling has no history, and a service that
reported a zero success ratio for it would argue against every recent
remediation for the sole reason that it is recent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import Episode, EpisodeOutcome, StoredStrategy, TenantScope
from platform.persistence.ports.remediation_ledger import (
    RemediationOutcome,
    VerificationState,
    VerificationVerdict,
)
from platform.remediation.history import (
    EPISODE_REMEDIATION_KEY,
    EffectivenessHistory,
    EffectivenessMemory,
    PriorEffectiveness,
)
from platform.remediation.obligations import Verification

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def an_outcome(
    *,
    action_id: str,
    verdict: VerificationVerdict | None,
    capability: str = "clear_cache",
    resource_id: str = "store-cove",
    condition_key: str = "datastore-near-full",
    minutes: float = 0.0,
    run_id: str = "run-1",
) -> RemediationOutcome:
    """Return one ledger row, verified or still settling."""
    return RemediationOutcome(
        action_id=action_id,
        capability=capability,
        resource_id=resource_id,
        condition_key=condition_key,
        team_node_id="team-payments",
        run_id=run_id,
        executed_at=at(minutes),
        due_at=at(minutes + 5),
        settle_seconds=300,
        state=(VerificationState.VERIFIED if verdict is not None else VerificationState.AWAITING),
        verdict=verdict,
        before={"filesystem.used_percent": 96.0},
        after={"filesystem.used_percent": 60.0} if verdict is not None else {},
    )


@pytest.fixture
async def storage() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    return store


async def test_a_capability_never_tried_here_says_so_rather_than_scoring_zero(
    storage: FakePersistence,
) -> None:
    """A proposal must be able to tell "new" from "never works"."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        prior = await EffectivenessHistory(ledger=unit.remediation).prior(
            "clear_cache", "store-cove"
        )

    assert not prior.known
    assert not prior.discouraged
    assert "has not been tried here before" in prior.describe()


async def test_a_capability_whose_attempts_are_all_settling_is_not_discouraged(
    storage: FakePersistence,
) -> None:
    """FR-015: "nothing is known yet" is a different answer from "it never works"."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        for index in range(3):
            await unit.remediation.record(
                an_outcome(action_id=f"action-{index}", verdict=None, minutes=index)
            )
        prior = await EffectivenessHistory(ledger=unit.remediation).prior(
            "clear_cache", "store-cove"
        )

    assert prior.summary.total == 3
    assert not prior.known
    assert not prior.discouraged
    assert prior.success_ratio == 0.0
    assert "none of them has finished settling" in prior.describe()


async def test_a_capability_that_has_never_worked_here_is_discouraged(
    storage: FakePersistence,
) -> None:
    """FR-015: this is the sentence a proposal reads and a reviewer sees."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.INEFFECTIVE)
        )
        await unit.remediation.record(
            an_outcome(action_id="b", verdict=VerificationVerdict.WORSENED, minutes=10)
        )
        prior = await EffectivenessHistory(ledger=unit.remediation).prior(
            "clear_cache", "store-cove"
        )

    assert prior.known
    assert prior.discouraged
    described = prior.describe()
    assert "worked 0 of them" in described
    assert "made things worse" in described
    assert "propose something else" in described
    assert prior.as_evidence().reference == "effectiveness:clear_cache@store-cove"


async def test_the_history_answers_by_resource_by_capability_and_by_condition(
    storage: FakePersistence,
) -> None:
    """FR-014: each dimension on its own, because they are three different claims."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.EFFECTIVE)
        )
        await unit.remediation.record(
            an_outcome(
                action_id="b",
                verdict=VerificationVerdict.INEFFECTIVE,
                resource_id="store-reef",
                minutes=1,
            )
        )
        await unit.remediation.record(
            an_outcome(
                action_id="c",
                verdict=VerificationVerdict.EFFECTIVE,
                capability="restart_workload",
                condition_key="pod-crashlooping",
                minutes=2,
            )
        )
        history = EffectivenessHistory(ledger=unit.remediation)

        by_resource = await history.by_resource("store-cove")
        by_capability = await history.by_capability("restart_workload")
        by_condition = await history.by_condition("datastore-near-full")
        recent = await history.recent(resource_id="store-cove")

    assert by_resource.total == 2
    assert by_capability.total == 1
    assert by_condition.total == 2
    assert [row.action_id for row in recent] == ["c", "a"]


async def test_the_condition_narrows_the_history_a_proposal_reads(
    storage: FakePersistence,
) -> None:
    """ "Works on this pod" and "works when the pod is out of memory" differ."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.EFFECTIVE)
        )
        await unit.remediation.record(
            an_outcome(
                action_id="b",
                verdict=VerificationVerdict.INEFFECTIVE,
                condition_key="datastore-write-latency",
                minutes=1,
            )
        )
        narrowed = await EffectivenessHistory(ledger=unit.remediation).prior(
            "clear_cache", "store-cove", condition_key="datastore-write-latency"
        )

    assert narrowed.summary.total == 1
    assert narrowed.success_ratio == 0.0


async def test_a_verdict_is_written_onto_the_run_s_episode_not_a_second_store(
    storage: FakePersistence,
) -> None:
    """FR-016 and T-024: the learning goes where the platform already learns."""
    episode = Episode(
        episode_id="episode-1",
        title="Datastore near full",
        summary="store-cove filled up",
        signature="sig-1",
        outcome=EpisodeOutcome.RESOLVED,
        run_id="run-1",
        occurred_at=at(),
        components=("datastore:store-cove",),
    )
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.episodes.save(episode)
        await unit.episodes.save_strategy(
            StoredStrategy(
                team_node_id="team-payments",
                issue_type="datastore-near-full",
                component_key="datastore:store-cove",
                content={"steps": ["clear the cache"]},
                generated_at=at(),
            )
        )

        outcome = an_outcome(action_id="a", verdict=VerificationVerdict.INEFFECTIVE)
        landed = await EffectivenessMemory(episodes=unit.episodes).record(
            Verification(
                outcome=outcome,
                verdict=VerificationVerdict.INEFFECTIVE,
                before=dict(outcome.before),
                after={"filesystem.used_percent": 95.0},
            )
        )

        stored = await unit.episodes.get_by_run("run-1")
        strategy = await unit.episodes.get_strategy(
            team_node_id="team-payments",
            issue_type="datastore-near-full",
            component_key="datastore:store-cove",
        )

    assert landed
    assert stored is not None
    recorded = stored.metadata[EPISODE_REMEDIATION_KEY]
    assert [item["verdict"] for item in recorded] == ["ineffective"]
    assert "remediation:ineffective" in stored.tags
    # The playbook said to clear the cache and the cache clear did not work, so
    # the playbook is stale rather than deleted.
    assert strategy is not None
    assert strategy.stale


async def test_a_verdict_about_a_run_that_wrote_no_episode_is_dropped_quietly(
    storage: FakePersistence,
) -> None:
    """An ablation turns memory writing off; the loop must still close."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = an_outcome(action_id="a", verdict=VerificationVerdict.EFFECTIVE)
        landed = await EffectivenessMemory(episodes=unit.episodes).record(
            Verification(outcome=outcome, verdict=VerificationVerdict.EFFECTIVE)
        )

    assert not landed


def test_the_record_a_surface_renders_carries_the_counts_and_the_sentence() -> None:
    """Two renderings of one history is two places for them to disagree."""
    prior = PriorEffectiveness(capability="clear_cache", resource_id="store-cove")

    record = prior.to_record()

    assert record["summary"] == prior.describe()
    assert record["known"] is False
    assert record["counts"] == {}


async def test_a_proposal_carries_what_has_worked_here_before(
    storage: FakePersistence,
) -> None:
    """SC-008's other half: the proposal reads it, and so does the reviewer.

    Through the real request builder rather than a double, because the failure
    this catches is the history being computed and then not reaching the
    payload — which every unit test on either side of the seam would miss.
    """
    from config.constants.closed_loop import REMEDIATION_PAYLOAD_EFFECTIVENESS
    from core.capability.metadata import SideEffectLevel
    from platform.remediation.history import LedgerEffectiveness
    from platform.remediation.models import RemediationAction, RemediationTarget
    from platform.remediation.request import RequestBuilder
    from platform.remediation.rollback.generator import PlanFactory

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.record(
            an_outcome(action_id="a", verdict=VerificationVerdict.INEFFECTIVE)
        )
        await unit.remediation.record(
            an_outcome(action_id="b", verdict=VerificationVerdict.WORSENED, minutes=10)
        )

    registry = _a_registry()
    builder = RequestBuilder(
        registry=registry,
        plans=PlanFactory(registry=registry, identifiers=lambda: "plan-1"),
        history=LedgerEffectiveness(gateway=storage, scope=TenantScope(org_id="acme")),
    )
    action = RemediationAction(
        action_id="action-9",
        capability="clear_cache",
        target=RemediationTarget(identifier="store-cove", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
    )

    request = await builder.build(action)

    assert request.prior is not None
    assert request.prior.discouraged
    # The model reads the rationale; the reviewer reads the payload. Both.
    assert "propose something else" in request.rationale()
    assert request.payload()[REMEDIATION_PAYLOAD_EFFECTIVENESS]["discouraged"] is True


def _a_registry():
    """Return a registry whose one capability can read and undo a cache clear."""
    from datetime import datetime as _datetime

    from platform.remediation.components import ComponentRegistry, RemediationComponents
    from platform.remediation.declaration import (
        SignalDirection,
        VerificationDeclaration,
        VerificationSignal,
    )
    from platform.remediation.models import (
        RollbackPlan,
        RollbackStep,
        StateSnapshot,
    )

    class Reader:
        """Reads a target that always answers."""

        async def read(self, action, *, at: _datetime) -> StateSnapshot:  # noqa: ANN001
            """Return a readable snapshot."""
            return StateSnapshot(target=str(action.target), observed_at=at, values={"entries": 12})

    class Generator:
        """Produces a plan that restores what was there."""

        def plan(self, action, *, before) -> RollbackPlan:  # noqa: ANN001
            """Return the plan restoring the recorded entries."""
            return RollbackPlan(
                plan_id="",
                action_id=action.action_id,
                target=str(action.target),
                recorded_state=before,
                summary="restore the cleared entries",
                steps=(RollbackStep(ordinal=1, description="restore", capability="clear_cache"),),
            )

    class Verifier:
        """Compares nothing, because this test never executes."""

        def verify(self, action, *, before, after) -> tuple[()]:  # noqa: ANN001
            """Return no divergences."""
            return ()

    return ComponentRegistry().register(
        RemediationComponents(
            capability="clear_cache",
            reader=Reader(),  # type: ignore[arg-type]
            applier=Reader(),  # type: ignore[arg-type]
            generator=Generator(),  # type: ignore[arg-type]
            verifier=Verifier(),  # type: ignore[arg-type]
            verification=VerificationDeclaration(
                signals=(
                    VerificationSignal(
                        name="filesystem.used_percent",
                        direction=SignalDirection.DOWN,
                        clears_at=80.0,
                    ),
                ),
                settle_seconds=300,
            ),
        )
    )
