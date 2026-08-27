"""Stage ordering, the merge, the failure contract, and the hook that fires once.

Everything here is deliberately boring, which is the point: the interesting
behaviour is in the stages, and the lifecycle's job is to be the one place
where the order, the merge, and the failure path are decided so no stage has an
opinion about any of them.

Four properties, each of which a test in this feature asserts.

**Order is fixed and checked at construction.** Six stages, in the declared
sequence. A pipeline assembled out of order fails when it is built,
not on the incident that first exercised the wrong one.

**One merge path.** Every stage's updates go through ``apply_state_updates``.

**A failure is recorded and re-raised.** The exception is annotated
with the stage it came out of and rises unchanged, so a caller that knows what
to do with a provider timeout still recognises one. Swallowing it would make a
stage that failed indistinguishable from a stage that had nothing to say.

**``on_run_end`` fires exactly once, whatever happened.** In a ``finally``, and
guarded, because episode extraction and every other downstream consumer is
built on the assumption that it runs once per investigation — twice is a
duplicated episode and none is a run that never entered the memory layer.

Halting is a property of the outcome rather than a flag the lifecycle keeps.
Intake marking an input as noise, deduplication linking it, and resolution
finding nothing to run with all end the run the same way: they write an outcome
whose kind says it halts, and the loop below stops asking for more stages.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from config.constants.runs import (
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
)
from core.pipeline.findings import finding_for
from core.pipeline.ownership import violations
from core.pipeline.stage import Stage, annotate_failure
from core.pipeline.streaming import EventStream, silent_stream
from core.state.agent_state import AgentState, apply_state_updates, changed_paths
from core.state.types import STAGE_ORDER, InvestigationOutcome, StageName
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class PipelineOrderError(Exception):
    """The stages a pipeline was built from are not in the declared order."""


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """One investigation's outcome, as the caller and the run-end hooks see it.

    Carried even when the run raised. A pipeline that failed in ``diagnose``
    still gathered evidence, and a hook that only ever saw successful runs
    would leave every failure out of the memory layer — which is the half worth
    learning from.
    """

    state: AgentState
    stages_run: tuple[StageName, ...] = ()
    failed_stage: StageName | None = None
    failure: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether every stage that ran completed."""
        return self.failed_stage is None

    @property
    def outcome(self) -> InvestigationOutcome | None:
        """Return why the run ended, if a stage said."""
        return self.state.investigation.outcome

    @property
    def halted_early(self) -> bool:
        """Return whether the run stopped before the last stage."""
        return len(self.stages_run) < len(STAGE_ORDER)


@runtime_checkable
class PipelineEndHook(Protocol):
    """Called once when an investigation ends, whatever its outcome."""

    async def __call__(self, run: PipelineRun) -> None:
        """Observe the end of ``run``."""


class Pipeline:
    """The six stages, run in order over one shared state.

    ``strict`` turns the ownership table from documentation into enforcement at
    run time. It is off by default because the purity test already fails the
    build on a violation and paying for the comparison on every incident buys
    nothing — and on in the synthetic harness, where a stage that has started
    writing outside its slice should fail the scenario rather than quietly
    change what the run produced.
    """

    def __init__(
        self,
        stages: Sequence[Stage],
        *,
        stream: EventStream | None = None,
        end_hooks: Sequence[PipelineEndHook] = (),
        strict: bool = False,
    ) -> None:
        _check_order(stages)
        self._stages = tuple(stages)
        self._stream = stream if stream is not None else silent_stream()
        self._end_hooks = tuple(end_hooks)
        self._strict = strict

    @property
    def stages(self) -> tuple[Stage, ...]:
        """Return the stages this pipeline runs, in order."""
        return self._stages

    @property
    def stage_names(self) -> tuple[StageName, ...]:
        """Return the names of the stages this pipeline runs, in order."""
        return tuple(stage.name for stage in self._stages)

    async def run(self, state: AgentState) -> PipelineRun:
        """Return the finished investigation, or re-raise what a stage raised.

        The run-end hooks fire on both paths, exactly once, before the
        exception continues on its way.
        """
        current = state
        completed: list[StageName] = []
        failed: StageName | None = None
        failure = ""

        try:
            for stage in self._stages:
                if current.investigation.halted:
                    break
                try:
                    current = await self._run_stage(stage, current)
                except BaseException as error:
                    failed, failure = stage.name, f"{type(error).__name__}: {error}"
                    await self._stream.error(stage.name, failure)
                    logger.error(
                        "pipeline.stage_failed",
                        run_id=current.run_id,
                        stage=stage.name.value,
                        error=failure,
                    )
                    # Annotate, then a bare ``raise``: the exception that leaves
                    # here is the one the stage raised, traceback included, with
                    # the stage's identity attached as a note.
                    annotate_failure(error, stage=stage.name, run_id=current.run_id)
                    raise
                completed.append(stage.name)
        finally:
            run = PipelineRun(
                state=current,
                stages_run=tuple(completed),
                failed_stage=failed,
                failure=failure,
            )
            await self._finish(run)

        return run

    async def _run_stage(self, stage: Stage, state: AgentState) -> AgentState:
        """Return the state after ``stage``, with its transitions on the stream."""
        await self._stream.stage_start(stage.name)
        updates = await stage(state)
        merged = apply_state_updates(state, updates)

        if self._strict:
            _check_purity(stage.name, state, merged)

        await self._stream.stage_end(
            stage.name,
            detail={
                "changed": ",".join(sorted(changed_paths(state, merged))),
                **_reckoning(stage.name, state, merged),
            },
        )
        return merged

    async def _finish(self, run: PipelineRun) -> None:
        """Emit the result and fire every end hook, once.

        A hook that raises is logged and the rest still run. One broken episode
        writer must not turn a completed investigation into a failed one, and
        the exception the run is already carrying — if it is — must not be
        replaced by a hook's.
        """
        outcome = run.outcome
        await self._stream.result(
            outcome.headline if outcome is not None else run.failure,
            detail={"kind": outcome.kind.value} if outcome is not None else {},
        )

        for hook in self._end_hooks:
            try:
                await hook(run)
            except Exception as error:
                logger.warning(
                    "pipeline.end_hook_failed",
                    run_id=run.state.run_id,
                    hook=type(hook).__name__,
                    error=str(error),
                )


def _reckoning(stage: StageName, before: AgentState, after: AgentState) -> dict[str, str]:
    """Return what ``stage`` established and what it spent establishing it.

    The spend is a *delta* across the stage, never the ledger. Every stage that
    calls a model adds to one accounting slice, so a stage reporting the slice
    would report the previous stages' spend as its own — and the two stages
    whose spend this exists to surface, intake and diagnosis, are the second and
    the fifth.

    Reporting it here rather than leaving it to a reader to subtract is what
    makes a run's token cost knowable at all. Only the gathering stage produces
    loop turns, so a total summed over the turn records is a floor: it omits
    both of the model calls the other stages made.
    """
    spent = after.accounting.tokens
    already = before.accounting.tokens
    return {
        STAGE_DETAIL_FINDING: finding_for(stage, after),
        STAGE_DETAIL_PROMPT_TOKENS: str(spent.total_input_tokens - already.total_input_tokens),
        STAGE_DETAIL_COMPLETION_TOKENS: str(spent.output_tokens - already.output_tokens),
        STAGE_DETAIL_LLM_CALLS: str(after.accounting.llm_calls - before.accounting.llm_calls),
    }


def _check_order(stages: Sequence[Stage]) -> None:
    """Raise unless ``stages`` are unique and in the declared pipeline order."""
    names = [stage.name for stage in stages]
    if len(set(names)) != len(names):
        raise PipelineOrderError(
            f"a stage appears more than once: {[name.value for name in names]}"
        )

    positions = [STAGE_ORDER.index(name) for name in names]
    if positions != sorted(positions):
        raise PipelineOrderError(
            "stages must run in the declared order "
            f"{[name.value for name in STAGE_ORDER]}, got {[name.value for name in names]}"
        )


def _check_purity(stage: StageName, before: AgentState, after: AgentState) -> None:
    """Raise when ``stage`` wrote outside the fields the ownership table gives it."""
    outside = violations(stage, changed_paths(before, after))
    if outside:
        raise PipelineOrderError(
            f"{stage.value} wrote outside its declared slice: {', '.join(outside)}"
        )


@dataclass(slots=True)
class CollectingEndHook:
    """Keeps every finished run. What a test and a single-process surface use."""

    runs: list[PipelineRun] = field(default_factory=list)

    async def __call__(self, run: PipelineRun) -> None:
        """Store ``run``."""
        self.runs.append(run)


#: A run-end hook expressed as a plain function, for a caller that has one.
EndHookFunction = Callable[[PipelineRun], Awaitable[None]]


__all__ = [
    "CollectingEndHook",
    "EndHookFunction",
    "Pipeline",
    "PipelineEndHook",
    "PipelineOrderError",
    "PipelineRun",
]
