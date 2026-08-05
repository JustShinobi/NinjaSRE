"""Sending a specialist to look at something, inside every bound the parent has.

Four things are enforced here, and each one is a way an unbounded sub-agent
system goes wrong.

**Depth.** A specialist that can dispatch a specialist can recurse, and a
recursion nobody bounded spends the whole budget one level down. A session at
``MAX_SUBAGENT_DEPTH`` is refused, and told so in words its model can act on.

**Budget.** A child derives its token budget from a share of its parent's, so a
parent that dispatches two specialists still has room left to reason about what
they found.

**Fan-out.** Concurrent dispatch is bounded lower than concurrent tool calls,
because each sub-agent is a whole loop that will itself run calls concurrently.

**Isolation.** The child gets a fresh session. Nothing of the parent's
transcript crosses, and only a ``Finding`` comes back — which is the whole
reason to dispatch rather than to keep reading in one context.

The runner is injected rather than imported. The loop supplies it, so this
module never has to know what a ``ReActLoop`` is, and the cycle that would
otherwise exist between the loop and its own sub-agents does not.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from config.constants.investigation import (
    MAX_PARALLEL_SUBAGENTS,
    MAX_SUBAGENT_DEPTH,
)
from config.prompts.investigation import SUBAGENT_DEPTH_REFUSED, SUBAGENT_UNKNOWN
from core.agent.execution import ExecutionBatch, ExecutionOutcome
from core.agent.session import Session
from core.agent.subagents.definition import SubAgent
from core.agent.subagents.findings import Finding, failed_finding
from core.agent.tool_cache import ToolCallCache
from core.agent.turn import GuardrailAction, GuardrailActionKind, ToolExecution
from core.capability.result import CapabilityErrorClass
from core.capability.telemetry import InvocationOutcome, filter_arguments
from core.llm.types import ToolCall, ToolResult, ToolSchema
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name the model calls to dispatch a specialist. Handled by the loop rather
#: than declared as a capability: dispatch needs the session, the depth, and the
#: runner, none of which a registered tool's signature can carry.
DISPATCH_CAPABILITY = "dispatch_subagent"

#: Returned when a specialist's capability subset is empty in this deployment.
NO_CAPABILITIES = (
    "The {name!r} specialist has no capabilities available in this deployment "
    "({needs}), so dispatching it would achieve nothing. Do the work with what you hold."
)

#: Returned when the arguments do not name a specialist and a task.
MALFORMED_DISPATCH = (
    "A dispatch needs both 'subagent' (the specialist to send) and 'task' (what to "
    "find out, stated in full — the specialist cannot see this conversation)."
)


@dataclass(frozen=True, slots=True)
class SubAgentRun:
    """What one dispatched specialist produced.

    ``guardrail_actions`` travels back with the finding so the parent's trace
    can say "the specialist I sent hit its iteration ceiling". Without it, a
    parent's trace shows a thin finding and no reason for it.
    """

    finding: Finding
    session: Session | None = None
    guardrail_actions: tuple[GuardrailAction, ...] = ()


class SubAgentRunner(Protocol):
    """Runs one specialist to completion and returns what it found."""

    async def __call__(self, definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        """Return the outcome of running ``definition`` against ``task``."""


@dataclass(frozen=True, slots=True)
class SubAgentCatalogue:
    """The specialists one loop may dispatch."""

    definitions: tuple[SubAgent, ...] = field(default_factory=tuple)

    def get(self, name: str) -> SubAgent | None:
        """Return the specialist called ``name``, or ``None``."""
        wanted = name.strip().lower()
        return next((item for item in self.definitions if item.name == wanted), None)

    def names(self) -> tuple[str, ...]:
        """Return every specialist's name, in declared order."""
        return tuple(item.name for item in self.definitions)

    def __bool__(self) -> bool:
        """Return whether any specialist is configured."""
        return bool(self.definitions)


def dispatch_schema(catalogue: SubAgentCatalogue) -> ToolSchema:
    """Return the tool schema the model uses to dispatch a specialist.

    The task description says the specialist cannot see this conversation. That
    sentence is doing real work: a model that assumes shared context writes
    "look into it" and gets back a finding about nothing.
    """
    return ToolSchema(
        name=DISPATCH_CAPABILITY,
        description=(
            "Send a specialist to investigate one question in isolation and return a "
            "structured finding. The specialist starts with no knowledge of this "
            "conversation, so state the task in full. Use this when a question needs "
            "sustained work in one area rather than one or two calls."
        ),
        parameters={
            "type": "object",
            "properties": {
                "subagent": {
                    "type": "string",
                    "enum": list(catalogue.names()),
                    "description": _specialist_menu(catalogue),
                },
                "task": {
                    "type": "string",
                    "description": (
                        "What to find out, stated in full and standing on its own. "
                        "Include the service, the time window, and what you already "
                        "believe — the specialist cannot see any of it otherwise."
                    ),
                },
            },
            "required": ["subagent", "task"],
        },
    )


def _specialist_menu(catalogue: SubAgentCatalogue) -> str:
    """Return the one-line-per-specialist description the enum is chosen from."""
    return "The specialist to send. " + " ".join(
        f"{item.name}: {item.description}" for item in catalogue.definitions
    )


def _refusal(
    call: ToolCall, message: str, kind: GuardrailActionKind, classification: CapabilityErrorClass
) -> tuple[ExecutionOutcome, GuardrailAction]:
    """Return a refused dispatch as a result the model can read."""
    return (
        ExecutionOutcome(
            execution=ToolExecution(
                call_id=call.id,
                capability=DISPATCH_CAPABILITY,
                arguments=filter_arguments(call.arguments),
                outcome=InvocationOutcome.FAILURE,
                denied=True,
                error_class=classification,
                error_message=message,
            ),
            tool_result=ToolResult(
                call_id=call.id, name=DISPATCH_CAPABILITY, content=message, is_error=True
            ),
        ),
        GuardrailAction(kind=kind, target=call.name, reason=message),
    )


def _arguments(call: ToolCall) -> tuple[str, str]:
    """Return the specialist name and task ``call`` asked for, blank when absent."""
    raw: Mapping[str, Any] = call.arguments
    return str(raw.get("subagent", "")).strip(), str(raw.get("task", "")).strip()


@dataclass(frozen=True, slots=True)
class SubAgentDispatcher:
    """Runs the dispatch calls in one turn, inside the parent's bounds."""

    catalogue: SubAgentCatalogue
    runner: SubAgentRunner
    available: Sequence[Any] = ()
    max_parallel: int = MAX_PARALLEL_SUBAGENTS
    max_depth: int = MAX_SUBAGENT_DEPTH

    async def dispatch(
        self,
        calls: Sequence[ToolCall],
        *,
        session: Session,
        cache: ToolCallCache,
        iteration: int,
    ) -> ExecutionBatch:
        """Run every dispatch call in one turn, bounded and isolated."""
        if not calls:
            return ExecutionBatch()

        limit = asyncio.Semaphore(max(self.max_parallel, 1))

        async def one(call: ToolCall) -> tuple[ExecutionOutcome, tuple[GuardrailAction, ...]]:
            async with limit:
                return await self._one(call, session=session, cache=cache, iteration=iteration)

        produced = await asyncio.gather(*(one(call) for call in calls))

        outcomes: list[ExecutionOutcome] = []
        actions: list[GuardrailAction] = []
        for outcome, guardrails in produced:
            outcomes.append(outcome)
            actions.extend(guardrails)

        return ExecutionBatch(outcomes=tuple(outcomes), guardrail_actions=tuple(actions))

    async def _one(
        self,
        call: ToolCall,
        *,
        session: Session,
        cache: ToolCallCache,
        iteration: int,
    ) -> tuple[ExecutionOutcome, tuple[GuardrailAction, ...]]:
        """Run one dispatch call, or refuse it."""
        if session.depth >= self.max_depth:
            outcome, action = _refusal(
                call,
                SUBAGENT_DEPTH_REFUSED.format(depth=session.depth),
                GuardrailActionKind.SUBAGENT_DEPTH_EXCEEDED,
                CapabilityErrorClass.PERMISSION_DENIED,
            )
            return outcome, (action,)

        name, task = _arguments(call)
        if not name or not task:
            outcome, action = _refusal(
                call,
                MALFORMED_DISPATCH,
                GuardrailActionKind.UNKNOWN_CAPABILITY,
                CapabilityErrorClass.INVALID_ARGUMENTS,
            )
            return outcome, (action,)

        definition = self.catalogue.get(name)
        if definition is None:
            outcome, action = _refusal(
                call,
                SUBAGENT_UNKNOWN.format(
                    name=name, available=", ".join(self.catalogue.names()) or "none"
                ),
                GuardrailActionKind.UNKNOWN_CAPABILITY,
                CapabilityErrorClass.NOT_FOUND,
            )
            return outcome, (action,)

        if not definition.subset(self.available):
            outcome, action = _refusal(
                call,
                NO_CAPABILITIES.format(
                    name=name,
                    needs=", ".join((*definition.capabilities, *definition.domains)) or "nothing",
                ),
                GuardrailActionKind.UNKNOWN_CAPABILITY,
                CapabilityErrorClass.UNAVAILABLE,
            )
            return outcome, (action,)

        cached = cache.get(DISPATCH_CAPABILITY, call.arguments)
        if cached is not None:
            return (
                ExecutionOutcome(
                    execution=ToolExecution(
                        call_id=call.id,
                        capability=DISPATCH_CAPABILITY,
                        arguments=filter_arguments(call.arguments),
                        replayed=True,
                        evidence_ids=cached.evidence_ids,
                    ),
                    tool_result=ToolResult(
                        call_id=call.id,
                        name=DISPATCH_CAPABILITY,
                        content=cached.replay_text(),
                    ),
                ),
                (
                    GuardrailAction(
                        kind=GuardrailActionKind.REPLAYED_DUPLICATE,
                        target=DISPATCH_CAPABILITY,
                        reason=f"{name} was already dispatched with this exact task",
                    ),
                ),
            )

        return await self._run(
            call, definition, task, session=session, cache=cache, iteration=iteration
        )

    async def _run(
        self,
        call: ToolCall,
        definition: SubAgent,
        task: str,
        *,
        session: Session,
        cache: ToolCallCache,
        iteration: int,
    ) -> tuple[ExecutionOutcome, tuple[GuardrailAction, ...]]:
        """Run one specialist and fold its finding into the parent's evidence."""
        try:
            run = await self.runner(definition, task, session)
        except asyncio.CancelledError:
            # Cancellation is the parent's decision travelling downward; it is
            # not a specialist failing, and swallowing it here would leave the
            # parent unable to stop.
            raise
        except Exception as error:  # noqa: BLE001 — FR-012: a specialist must not fail the parent
            logger.warning(
                "agent.subagent_failed",
                session_id=session.id,
                subagent=definition.name,
                error=str(error),
            )
            run = SubAgentRun(
                finding=failed_finding(definition.name, f"{type(error).__name__}: {error}")
            )

        finding = run.finding
        entry = session.record_evidence(finding.as_evidence(iteration=iteration, call_id=call.id))
        content = finding.render()
        cache.put(
            DISPATCH_CAPABILITY,
            call.arguments,
            content=content,
            is_error=finding.failed,
            evidence_ids=(entry.id,),
        )

        return (
            ExecutionOutcome(
                execution=ToolExecution(
                    call_id=call.id,
                    capability=DISPATCH_CAPABILITY,
                    arguments=filter_arguments(call.arguments),
                    outcome=(
                        InvocationOutcome.FAILURE if finding.failed else InvocationOutcome.SUCCESS
                    ),
                    error_message=finding.headline if finding.failed else "",
                    evidence_ids=(entry.id,),
                ),
                tool_result=ToolResult(
                    call_id=call.id,
                    name=DISPATCH_CAPABILITY,
                    content=content,
                    is_error=finding.failed,
                ),
                evidence=(entry,),
            ),
            # The child's bounds are the parent's business: a thin finding with
            # no explanation is what a trace looks like when this is dropped.
            tuple(
                GuardrailAction(
                    kind=action.kind,
                    target=f"{definition.name}:{action.target}",
                    reason=action.reason,
                )
                for action in run.guardrail_actions
            ),
        )


#: How a child's token budget is derived, exposed so the loop and the tests
#: agree on the arithmetic rather than each doing their own.
def child_budget(parent: Session, definition: SubAgent) -> int:
    """Return the context budget a child of ``parent`` runs under."""
    if parent.context_budget_tokens <= 0:
        return 0
    return max(int(parent.context_budget_tokens * definition.token_budget_ratio), 1)


DISPATCH_CAPABILITY_NAME: Final[str] = DISPATCH_CAPABILITY


__all__ = [
    "DISPATCH_CAPABILITY",
    "DISPATCH_CAPABILITY_NAME",
    "MALFORMED_DISPATCH",
    "NO_CAPABILITIES",
    "SubAgentCatalogue",
    "SubAgentDispatcher",
    "SubAgentRun",
    "SubAgentRunner",
    "child_budget",
    "dispatch_schema",
]
