"""The order, the merge, the failure contract, and the hook that fires once.

Four properties, and each of them is the kind that only fails in production if
nothing asserts it here: a pipeline assembled out of order, a stage failure
that vanished, a run-end hook that fired twice, and a halt that did not halt.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.domain.diagnosis.result import Diagnosis
from core.domain.diagnosis.taxonomy import RootCauseCategory
from core.pipeline.lifecycle import (
    CollectingEndHook,
    Pipeline,
    PipelineOrderError,
    PipelineRun,
)
from core.pipeline.ports import DeliveryPayload, FixedCatalogueResolver, StaticCatalogue
from core.pipeline.stage import STAGE_FAILURE_NOTE
from core.pipeline.stages.deliver import DeliverStage
from core.pipeline.stages.resolve_integrations import ResolveIntegrationsStage
from core.pipeline.streaming import (
    EventStream,
    PipelineEventKind,
    RecordingSink,
    replay,
)
from core.state.agent_state import AgentState, StateUpdates
from core.state.types import InvestigationOutcome, OutcomeKind, StageName
from tests.unit.core.pipeline.conftest import alertmanager_state, tool

pytestmark = pytest.mark.unit


class _Stage:
    """A stage that returns what a test told it to, or raises."""

    def __init__(
        self,
        name: StageName,
        *,
        updates: StateUpdates | None = None,
        raises: BaseException | None = None,
    ) -> None:
        self.name = name
        self._updates = updates if updates is not None else StateUpdates()
        self._raises = raises
        self.calls = 0

    async def __call__(self, state: AgentState) -> StateUpdates:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._updates


class _Destination:
    def __init__(self, name: str, *, fails: bool = False) -> None:
        self.name = name
        self._fails = fails
        self.received: list[DeliveryPayload] = []

    async def deliver(self, payload: DeliveryPayload) -> str:
        if self._fails:
            raise ConnectionError("the workspace is unreachable")
        self.received.append(payload)
        return f"https://{self.name}.example/1"


def _halting(name: StageName, kind: OutcomeKind = OutcomeKind.NOISE) -> _Stage:
    return _Stage(
        name,
        updates=StateUpdates(
            investigation=replace(
                alertmanager_state().investigation,
                outcome=InvestigationOutcome(kind=kind, headline="stopped here"),
            )
        ),
    )


# -- ordering -----------------------------------------------------------------


def test_stages_must_be_in_the_declared_order() -> None:
    with pytest.raises(PipelineOrderError, match="declared order"):
        Pipeline([_Stage(StageName.DIAGNOSE), _Stage(StageName.INTAKE)])


def test_a_stage_may_not_appear_twice() -> None:
    with pytest.raises(PipelineOrderError, match="more than once"):
        Pipeline([_Stage(StageName.INTAKE), _Stage(StageName.INTAKE)])


def test_a_subset_in_order_is_allowed() -> None:
    pipeline = Pipeline([_Stage(StageName.INTAKE), _Stage(StageName.DELIVER)])

    assert pipeline.stage_names == (StageName.INTAKE, StageName.DELIVER)


def test_the_built_pipeline_runs_all_six_in_order() -> None:
    from core.pipeline.build import build_pipeline
    from core.state.types import STAGE_ORDER
    from tests.unit.core.pipeline.conftest import ScriptedLLM, ScriptedRuntime

    pipeline = build_pipeline(llm=ScriptedLLM(), runtime=ScriptedRuntime())

    assert pipeline.stage_names == STAGE_ORDER


# -- running ------------------------------------------------------------------


async def test_every_stage_runs_and_the_state_comes_back() -> None:
    stages = [_Stage(StageName.INTAKE), _Stage(StageName.DIAGNOSE)]
    pipeline = Pipeline(stages)

    run = await pipeline.run(alertmanager_state())

    assert [stage.calls for stage in stages] == [1, 1]
    assert run.succeeded
    assert run.stages_run == (StageName.INTAKE, StageName.DIAGNOSE)


async def test_every_transition_reaches_the_stream() -> None:
    sink = RecordingSink()
    pipeline = Pipeline([_Stage(StageName.INTAKE)], stream=EventStream("run-1", (sink,)))

    await pipeline.run(alertmanager_state())

    kinds = [event.kind for event in sink.events]
    assert kinds == [
        PipelineEventKind.STAGE_START,
        PipelineEventKind.STAGE_END,
        PipelineEventKind.RESULT,
    ]


async def test_a_halting_outcome_stops_the_remaining_stages() -> None:
    """Noise rejection at the lifecycle level: nothing after intake gets to run."""
    later = _Stage(StageName.GATHER_EVIDENCE)
    pipeline = Pipeline([_halting(StageName.INTAKE), later])

    run = await pipeline.run(alertmanager_state())

    assert later.calls == 0
    assert run.halted_early
    assert run.outcome is not None
    assert run.outcome.kind is OutcomeKind.NOISE


async def test_a_non_halting_outcome_does_not_stop_the_run() -> None:
    """A failed gathering run still gets diagnosed and delivered."""
    later = _Stage(StageName.DIAGNOSE)
    pipeline = Pipeline([_halting(StageName.INTAKE, OutcomeKind.FAILED), later])

    await pipeline.run(alertmanager_state())

    assert later.calls == 1


# -- the failure contract -----------------------------------------------------


async def test_a_stage_failure_is_re_raised_unchanged() -> None:
    """A caller that knows what to do with a provider timeout must still
    recognise one."""
    pipeline = Pipeline([_Stage(StageName.INTAKE, raises=TimeoutError("the provider hung"))])

    with pytest.raises(TimeoutError, match="the provider hung"):
        await pipeline.run(alertmanager_state())


async def test_a_stage_failure_carries_the_stage_that_produced_it() -> None:
    pipeline = Pipeline([_Stage(StageName.DIAGNOSE, raises=ValueError("bad schema"))])

    with pytest.raises(ValueError) as caught:
        await pipeline.run(alertmanager_state())

    expected = STAGE_FAILURE_NOTE.format(stage=StageName.DIAGNOSE.value, run_id="run-1")
    assert expected in caught.value.__notes__


async def test_a_stage_failure_reaches_the_stream_before_it_is_raised() -> None:
    sink = RecordingSink()
    pipeline = Pipeline(
        [_Stage(StageName.INTAKE, raises=RuntimeError("boom"))],
        stream=EventStream("run-1", (sink,)),
    )

    with pytest.raises(RuntimeError):
        await pipeline.run(alertmanager_state())

    view = replay(sink.events)
    assert view.failed
    assert view.stage(StageName.INTAKE) is not None
    assert view.stage(StageName.INTAKE).failed  # type: ignore[union-attr]


async def test_a_stage_failure_is_never_swallowed_into_empty_updates() -> None:
    """A stage that failed must not look like a stage that had nothing to say."""
    later = _Stage(StageName.DELIVER)
    pipeline = Pipeline([_Stage(StageName.INTAKE, raises=RuntimeError("boom")), later])

    with pytest.raises(RuntimeError):
        await pipeline.run(alertmanager_state())

    assert later.calls == 0


# -- the run-end hook ---------------------------------------------------------


async def test_the_end_hook_fires_exactly_once_on_a_completed_run() -> None:
    hook = CollectingEndHook()
    pipeline = Pipeline([_Stage(StageName.INTAKE)], end_hooks=(hook,))

    await pipeline.run(alertmanager_state())

    assert len(hook.runs) == 1
    assert hook.runs[0].succeeded


async def test_the_end_hook_fires_exactly_once_on_the_error_path() -> None:
    """A run that failed is the half worth learning from, and a hook that never
    saw it would leave every failure out of the memory layer."""
    hook = CollectingEndHook()
    pipeline = Pipeline([_Stage(StageName.INTAKE, raises=RuntimeError("boom"))], end_hooks=(hook,))

    with pytest.raises(RuntimeError):
        await pipeline.run(alertmanager_state())

    assert len(hook.runs) == 1
    assert not hook.runs[0].succeeded
    assert hook.runs[0].failed_stage is StageName.INTAKE
    assert "boom" in hook.runs[0].failure


async def test_the_end_hook_fires_exactly_once_on_a_halted_run() -> None:
    hook = CollectingEndHook()
    pipeline = Pipeline([_halting(StageName.INTAKE)], end_hooks=(hook,))

    await pipeline.run(alertmanager_state())

    assert len(hook.runs) == 1


async def test_a_broken_end_hook_does_not_change_the_run() -> None:
    """One broken episode writer must not turn a completed investigation into a
    failed one."""

    async def broken(run: PipelineRun) -> None:
        raise RuntimeError("the store is down")

    good = CollectingEndHook()
    pipeline = Pipeline([_Stage(StageName.INTAKE)], end_hooks=(broken, good))

    run = await pipeline.run(alertmanager_state())

    assert run.succeeded
    assert len(good.runs) == 1


async def test_a_broken_end_hook_does_not_replace_the_exception_a_run_is_carrying() -> None:
    async def broken(run: PipelineRun) -> None:
        raise RuntimeError("the store is down")

    pipeline = Pipeline(
        [_Stage(StageName.INTAKE, raises=TimeoutError("the provider hung"))],
        end_hooks=(broken,),
    )

    with pytest.raises(TimeoutError):
        await pipeline.run(alertmanager_state())


# -- strict purity ------------------------------------------------------------


async def test_strict_mode_fails_a_stage_that_writes_outside_its_slice() -> None:
    straying = _Stage(
        StageName.PLAN_EVIDENCE,
        updates=StateUpdates(
            investigation=replace(
                alertmanager_state().investigation, conclusion="written by the wrong stage"
            )
        ),
    )
    pipeline = Pipeline([straying], strict=True)

    with pytest.raises(PipelineOrderError, match="outside its declared slice"):
        await pipeline.run(alertmanager_state())


async def test_strict_mode_is_off_by_default() -> None:
    straying = _Stage(
        StageName.PLAN_EVIDENCE,
        updates=StateUpdates(
            investigation=replace(
                alertmanager_state().investigation, conclusion="written by the wrong stage"
            )
        ),
    )

    run = await Pipeline([straying]).run(alertmanager_state())

    assert run.succeeded


# -- delivery -----------------------------------------------------------------


def _delivered_state() -> AgentState:
    state = alertmanager_state()
    return replace(
        state,
        investigation=replace(
            state.investigation,
            diagnosis=Diagnosis(
                root_cause="the checkout container exceeded its memory limit",
                root_cause_category=RootCauseCategory.RESOURCE_EXHAUSTION,
                remediation_steps=("raise the memory limit",),
                confidence=0.8,
            ),
        ),
    )


async def test_the_report_reaches_every_configured_destination() -> None:
    slack, tracker = _Destination("slack"), _Destination("jira")

    updates = await DeliverStage((slack, tracker))(_delivered_state())

    assert updates.investigation is not None
    delivery = updates.investigation.delivery
    assert delivery is not None
    assert delivery.delivered == ("slack", "jira")
    assert delivery.complete
    assert len(slack.received) == 1


async def test_one_destination_failing_does_not_prevent_the_others() -> None:
    """Three destinations out of four is a delivered investigation."""
    broken, good = _Destination("slack", fails=True), _Destination("jira")

    updates = await DeliverStage((broken, good))(_delivered_state())

    delivery = updates.investigation.delivery  # type: ignore[union-attr]
    assert delivery is not None
    assert delivery.delivered == ("jira",)
    assert delivery.failed == ("slack",)
    assert not delivery.complete
    assert len(good.received) == 1


async def test_a_delivery_failure_is_recorded_with_its_reason() -> None:
    updates = await DeliverStage((_Destination("slack", fails=True),))(_delivered_state())

    delivery = updates.investigation.delivery  # type: ignore[union-attr]
    assert delivery is not None
    attempt = delivery.attempts[0]
    assert not attempt.delivered
    assert "ConnectionError" in attempt.failure
    assert "unreachable" in attempt.detail


async def test_the_outcome_names_the_cause_and_where_the_report_went() -> None:
    updates = await DeliverStage((_Destination("slack"),))(_delivered_state())

    outcome = updates.investigation.outcome  # type: ignore[union-attr]
    assert outcome is not None
    assert outcome.kind is OutcomeKind.DIAGNOSED
    assert "resource_exhaustion" in outcome.headline
    assert "slack" in outcome.detail
    assert outcome.next_steps == ("raise the memory limit",)


async def test_no_destination_configured_still_produces_the_report() -> None:
    updates = await DeliverStage()(_delivered_state())

    outcome = updates.investigation.outcome  # type: ignore[union-attr]
    assert outcome is not None
    assert outcome.kind is OutcomeKind.DIAGNOSED
    assert "not shipped" in outcome.detail


async def test_a_run_that_failed_is_still_reported_as_failed_after_delivery() -> None:
    """Delivery ships the report; it does not overturn the run's own verdict.

    Gathering records ``FAILED`` when the runtime produced nothing usable, and
    that outcome deliberately does not halt the run — the remaining stages
    still say what little can be said. What they must not do is replace it: a
    caller reading the finished state to decide whether the run completed would
    otherwise be told "diagnosed" about an investigation that gathered nothing,
    and the reason the runtime gave would be gone with it.
    """
    state = _delivered_state()
    failed = replace(
        state,
        investigation=replace(
            state.investigation,
            outcome=InvestigationOutcome(
                kind=OutcomeKind.FAILED,
                headline="Investigation did not complete",
                detail="the provider stopped answering",
            ),
        ),
    )

    updates = await DeliverStage((_Destination("slack"),))(failed)

    outcome = updates.investigation.outcome  # type: ignore[union-attr]
    assert outcome is not None
    assert outcome.kind is OutcomeKind.FAILED
    assert outcome.detail == "the provider stopped answering"
    assert updates.investigation.delivery is not None, (  # type: ignore[union-attr]
        "the report was withheld as well, which is not what this preserves"
    )


async def test_delivery_never_executes_a_remediation_step() -> None:
    """The steps are recommendations for a human until the remediation feature
    gates them, and this is the last place they pass through."""
    destination = _Destination("slack")

    await DeliverStage((destination,))(_delivered_state())

    payload = destination.received[0]
    assert payload.diagnosis.remediation_steps == ("raise the memory limit",)
    assert payload.state.investigation.delivery is None, "the payload is the state as it was"


async def test_a_catalogue_reaching_delivery_is_the_one_resolution_produced() -> None:
    found = tool("datadog_log_statistics")
    resolver = FixedCatalogueResolver(
        StaticCatalogue(tools=(found,), declarations=(found.metadata,))
    )

    updates = await ResolveIntegrationsStage(resolver)(alertmanager_state())

    assert updates.investigation is not None
    assert updates.investigation.catalogue.tool("datadog_log_statistics") is found
