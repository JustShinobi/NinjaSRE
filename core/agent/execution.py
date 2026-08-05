"""Running the calls a turn asked for, and turning each one into a record.

Three things happen here that the loop should not have to think about.

**A call the model invented is refused as a value.** The provider client already
drops calls to tools it never sent, but a name that was on the turn and is not
in this loop's tool set still reaches here — a sub-agent's subset is narrower
than its parent's. The model gets a structured error naming what it may call,
which it can act on, rather than an exception it never sees.

**A repeat is served from the cache and said to be a repeat.** See
``tool_cache``: the sentence matters more than the saved round trip.

**Every call produces evidence, whether or not the tool declared any.** A tool
that returns a dictionary and no ``Evidence`` still made an observation, and an
observation the context budget cannot see is one it cannot weigh.

Failures never propagate. ``RegisteredTool.invoke`` already converts an
exception into a classified result; this module keeps that property across a
batch, so one dead vendor costs one call rather than the turn.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.investigation import MAX_PARALLEL_TOOL_CALLS
from core.agent.hooks.registry import NO_HOOKS, HookRegistry
from core.agent.hooks.types import Deny, ToolContext
from core.agent.session import EvidenceEntry, Session
from core.agent.tool_cache import ToolCallCache
from core.agent.turn import GuardrailAction, GuardrailActionKind, HookFailure, ToolExecution
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityErrorClass, CapabilityResult
from core.capability.telemetry import InvocationOutcome, filter_arguments
from core.llm.types import ToolCall, ToolResult

#: What the model is told when it calls something this loop does not hold.
UNKNOWN_CAPABILITY_MESSAGE = (
    "{name!r} is not a capability you can call in this investigation. "
    "The capabilities available to you are: {available}."
)

#: Summary written for a tool that produced a result but declared no evidence
#: contract of its own.
IMPLICIT_EVIDENCE_SUMMARY = "{capability} returned a result for {arguments}"


def render_value(value: Any) -> str:
    """Return ``value`` as the text a model reads.

    JSON where it serialises, ``str`` where it does not. A tool returning
    something exotic is a reason for an ugly tool result, never a reason for a
    lost turn.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """One call's record, its reply to the model, and the evidence it produced."""

    execution: ToolExecution
    tool_result: ToolResult
    evidence: tuple[EvidenceEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionBatch:
    """Everything one turn's tool calls produced."""

    outcomes: tuple[ExecutionOutcome, ...] = ()
    guardrail_actions: tuple[GuardrailAction, ...] = ()
    hook_failures: tuple[HookFailure, ...] = ()

    @property
    def executions(self) -> tuple[ToolExecution, ...]:
        """Return the per-call records, in the order the model asked for them."""
        return tuple(outcome.execution for outcome in self.outcomes)

    @property
    def tool_results(self) -> tuple[ToolResult, ...]:
        """Return the replies that go back to the model."""
        return tuple(outcome.tool_result for outcome in self.outcomes)


def _evidence_from_result(
    call: ToolCall,
    result: CapabilityResult,
    *,
    registered: RegisteredTool,
    iteration: int,
    origin: str,
    content: str,
) -> tuple[EvidenceEntry, ...]:
    """Return the entries one successful call contributes to the session."""
    if result.evidence:
        return tuple(
            EvidenceEntry(
                id="",
                capability=call.name,
                summary=item.summary,
                evidence_type=item.evidence_type,
                source=item.source,
                content=content,
                reference=item.reference,
                call_id=call.id,
                iteration=iteration,
                origin=origin,
            )
            for item in result.evidence
        )

    return (
        EvidenceEntry(
            id="",
            capability=call.name,
            summary=IMPLICIT_EVIDENCE_SUMMARY.format(
                capability=call.name, arguments=render_value(filter_arguments(call.arguments))
            ),
            evidence_type=registered.metadata.evidence_type,
            source=registered.metadata.evidence_source,
            content=content,
            call_id=call.id,
            iteration=iteration,
            origin=origin,
        ),
    )


def _unknown_capability(
    call: ToolCall, *, available: Sequence[str]
) -> tuple[ExecutionOutcome, GuardrailAction]:
    """Return the refusal for a capability this loop does not hold."""
    message = UNKNOWN_CAPABILITY_MESSAGE.format(
        name=call.name, available=", ".join(sorted(available)) or "none"
    )
    return (
        ExecutionOutcome(
            execution=ToolExecution(
                call_id=call.id,
                capability=call.name,
                arguments=filter_arguments(call.arguments),
                outcome=InvocationOutcome.FAILURE,
                denied=True,
                error_class=CapabilityErrorClass.NOT_FOUND,
                error_message=message,
            ),
            tool_result=ToolResult(call_id=call.id, name=call.name, content=message, is_error=True),
        ),
        GuardrailAction(
            kind=GuardrailActionKind.UNKNOWN_CAPABILITY,
            target=call.name,
            reason="the model called a capability that was not on this turn",
        ),
    )


def _denied(call: ToolCall, decision: Deny) -> tuple[ExecutionOutcome, GuardrailAction]:
    """Return the structured refusal a ``pre_tool_use`` denial produces.

    The model is told, in a tool result it can read, that the call did not run
    and why. A denial the model cannot see is one it repeats every turn until
    the iteration ceiling ends the run.
    """
    return (
        ExecutionOutcome(
            execution=ToolExecution(
                call_id=call.id,
                capability=call.name,
                arguments=filter_arguments(call.arguments),
                outcome=InvocationOutcome.FAILURE,
                denied=True,
                error_class=decision.classification,
                error_message=decision.reason,
            ),
            tool_result=ToolResult(
                call_id=call.id, name=call.name, content=decision.reason, is_error=True
            ),
        ),
        GuardrailAction(
            kind=GuardrailActionKind.CALL_DENIED,
            target=call.name,
            reason=decision.reason,
        ),
    )


async def execute_call(
    call: ToolCall,
    *,
    registered: RegisteredTool,
    session: Session,
    cache: ToolCallCache,
    iteration: int,
    origin: str = "",
    hooks: HookRegistry = NO_HOOKS,
) -> tuple[ExecutionOutcome, tuple[GuardrailAction, ...], tuple[HookFailure, ...]]:
    """Run one call, or replay it, and return its record.

    Never raises. ``RegisteredTool.invoke`` converts a tool's exception into a
    classified result, and everything above that point here is arithmetic.

    ``pre_tool_use`` runs before the cache is consulted. A call somebody would
    refuse must not be served from memory either — a replayed denial is still a
    result the model was not allowed to have.
    """
    context = ToolContext(session=session, iteration=iteration, registered=registered)
    decision, arguments, hook_failures = await hooks.run_pre_tool_use(call, context)

    if isinstance(decision, Deny):
        outcome, action = _denied(call, decision)
        return outcome, (action,), hook_failures

    actions: list[GuardrailAction] = []
    if arguments != dict(call.arguments):
        actions.append(
            GuardrailAction(
                kind=GuardrailActionKind.ARGUMENTS_REWRITTEN,
                target=call.name,
                reason="a pre_tool_use hook replaced the arguments before dispatch",
            )
        )
        call = ToolCall(id=call.id, name=call.name, arguments=arguments)

    cached = cache.get(call.name, call.arguments)
    if cached is not None:
        return (
            ExecutionOutcome(
                execution=ToolExecution(
                    call_id=call.id,
                    capability=call.name,
                    arguments=filter_arguments(call.arguments),
                    outcome=(
                        InvocationOutcome.FAILURE if cached.is_error else InvocationOutcome.SUCCESS
                    ),
                    replayed=True,
                    evidence_ids=cached.evidence_ids,
                ),
                tool_result=ToolResult(
                    call_id=call.id,
                    name=call.name,
                    content=cached.replay_text(),
                    is_error=cached.is_error,
                ),
            ),
            (
                *actions,
                GuardrailAction(
                    kind=GuardrailActionKind.REPLAYED_DUPLICATE,
                    target=call.name,
                    reason="identical name and arguments to a call already made in this run",
                ),
            ),
            hook_failures,
        )

    invoked = await registered.invoke(call.arguments)
    result, post_failures = await hooks.run_post_tool_use(call, invoked, context)
    hook_failures = (*hook_failures, *post_failures)
    content = (
        render_value(result.value)
        if result.succeeded
        else f"{result.error.message}\n{result.error.detail}".strip()
        if result.error
        else ""
    )

    evidence: tuple[EvidenceEntry, ...] = ()
    if result.succeeded:
        drafted = _evidence_from_result(
            call,
            result,
            registered=registered,
            iteration=iteration,
            origin=origin,
            content=content,
        )
        evidence = tuple(session.record_evidence(entry) for entry in drafted)

    evidence_ids = tuple(entry.id for entry in evidence)
    cache.put(
        call.name,
        call.arguments,
        content=content,
        is_error=not result.succeeded,
        evidence_ids=evidence_ids,
    )

    return (
        ExecutionOutcome(
            execution=ToolExecution(
                call_id=call.id,
                capability=call.name,
                arguments=filter_arguments(call.arguments),
                outcome=(
                    InvocationOutcome.SUCCESS if result.succeeded else InvocationOutcome.FAILURE
                ),
                duration_seconds=result.duration_seconds,
                error_class=result.error.classification if result.error else None,
                error_message=result.error.message if result.error else "",
                evidence_ids=evidence_ids,
            ),
            tool_result=ToolResult(
                call_id=call.id,
                name=call.name,
                content=content,
                is_error=not result.succeeded,
            ),
            evidence=evidence,
        ),
        tuple(actions),
        hook_failures,
    )


async def execute_calls(
    calls: Sequence[ToolCall],
    *,
    tools: Mapping[str, RegisteredTool],
    session: Session,
    cache: ToolCallCache,
    iteration: int,
    origin: str = "",
    hooks: HookRegistry = NO_HOOKS,
) -> ExecutionBatch:
    """Run every call in one turn and return the batch record.

    Serial, in the order the model asked. Bounded concurrency for the calls
    whose authors declared them ``parallel_safe`` is layered on this in
    ``dispatch_calls``; the ordering guarantee here is what that one degrades to
    when nothing is parallel-safe.
    """
    outcomes: list[ExecutionOutcome] = []
    actions: list[GuardrailAction] = []
    failures: list[HookFailure] = []

    for call in calls:
        registered = tools.get(call.name)
        if registered is None:
            outcome, action = _unknown_capability(call, available=tuple(tools))
            outcomes.append(outcome)
            actions.append(action)
            continue

        outcome, produced, hook_failures = await execute_call(
            call,
            registered=registered,
            session=session,
            cache=cache,
            iteration=iteration,
            origin=origin,
            hooks=hooks,
        )
        outcomes.append(outcome)
        actions.extend(produced)
        failures.extend(hook_failures)

    return ExecutionBatch(
        outcomes=tuple(outcomes),
        guardrail_actions=tuple(actions),
        hook_failures=tuple(failures),
    )


def _parallel_safe(call: ToolCall, tools: Mapping[str, RegisteredTool]) -> bool:
    """Return whether ``call``'s author declared it safe to run alongside others.

    An unknown capability counts as safe: it never runs, it returns a refusal
    immediately, and treating it as a barrier would serialise a batch around a
    call the model got wrong.
    """
    registered = tools.get(call.name)
    return registered is None or registered.metadata.parallel_safe


def _groups(calls: Sequence[ToolCall], tools: Mapping[str, RegisteredTool]) -> list[list[ToolCall]]:
    """Return the calls split into runs that may execute together.

    Only *consecutive* parallel-safe calls are grouped. Pulling a safe call
    across a serial one to fill a batch would reorder the two, which is the
    same mistake as running them together — the author who set
    ``parallel_safe=False`` was making a claim about what may happen at the same
    time as this call, and "before" and "after" are part of that claim.
    """
    groups: list[list[ToolCall]] = []
    for call in calls:
        if _parallel_safe(call, tools) and groups and _parallel_safe(groups[-1][0], tools):
            groups[-1].append(call)
        else:
            groups.append([call])
    return groups


async def dispatch_calls(
    calls: Sequence[ToolCall],
    *,
    tools: Mapping[str, RegisteredTool],
    session: Session,
    cache: ToolCallCache,
    iteration: int,
    origin: str = "",
    hooks: HookRegistry = NO_HOOKS,
    max_parallel: int = MAX_PARALLEL_TOOL_CALLS,
) -> ExecutionBatch:
    """Run one turn's calls, concurrently where their authors allowed it.

    Results come back in the order the model asked for them, whatever order they
    finished in. A model reading its own tool results out of order would draw
    conclusions from a sequence that never happened, and the trajectory scorer
    treats a concurrent batch as an unordered set precisely so that the record
    does not claim one.
    """
    if not calls:
        return ExecutionBatch()

    limit = asyncio.Semaphore(max(max_parallel, 1))
    outcomes: list[ExecutionOutcome] = []
    actions: list[GuardrailAction] = []
    failures: list[HookFailure] = []

    async def one(
        call: ToolCall,
    ) -> tuple[ExecutionOutcome, tuple[GuardrailAction, ...], tuple[HookFailure, ...]]:
        registered = tools.get(call.name)
        if registered is None:
            outcome, action = _unknown_capability(call, available=tuple(tools))
            return outcome, (action,), ()

        async with limit:
            return await execute_call(
                call,
                registered=registered,
                session=session,
                cache=cache,
                iteration=iteration,
                origin=origin,
                hooks=hooks,
            )

    for group in _groups(calls, tools):
        if len(group) == 1:
            produced = [await one(group[0])]
        else:
            produced = list(await asyncio.gather(*(one(call) for call in group)))
        for outcome, guardrails, hook_failures in produced:
            outcomes.append(outcome)
            actions.extend(guardrails)
            failures.extend(hook_failures)

    return ExecutionBatch(
        outcomes=tuple(outcomes),
        guardrail_actions=tuple(actions),
        hook_failures=tuple(failures),
    )


__all__ = [
    "IMPLICIT_EVIDENCE_SUMMARY",
    "UNKNOWN_CAPABILITY_MESSAGE",
    "ExecutionBatch",
    "ExecutionOutcome",
    "dispatch_calls",
    "execute_call",
    "execute_calls",
    "render_value",
]
