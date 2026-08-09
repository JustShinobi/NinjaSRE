"""The canonical loop: think, select, execute, observe — inside every bound.

This is the runtime whose behaviour defines correctness (Article V). Everything
Article II names lives in this control flow, and lives here rather than in a
decorator or a wrapper because each one needs to see the loop's state at a
specific point:

- the **iteration ceiling** and the **wall clock**, checked before a turn is
  built, because a run that blocks for an hour on one call has consumed no
  iterations at all;
- the **duplicate cache**, consulted during execution, because that is where a
  repeat can still be turned into a sentence the model reads;
- the **stagnation breaker**, evaluated after execution, because "produced no
  fresh evidence" is a fact about what the calls returned;
- the **context budget**, applied before every model call, because that is the
  only moment at which what will be sent is known.

There is one more property worth stating plainly: **the loop never raises at the
caller**. A provider failure becomes a partial result carrying the evidence
gathered so far; a tool exception is already a classified value by the time it
arrives. An investigation that lost its model after eleven observations has
produced eleven observations, and the operator in the incident would like them.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime

from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from config.prompts.investigation import (
    DEFAULT_RUNTIME_SYSTEM_PROMPT,
    SUBAGENT_SYSTEM_PROMPT,
)
from core.agent.compaction import apply_compaction
from core.agent.conclusion import AcceptAnyAnswer, ConclusionPolicy
from core.agent.context_budget import BudgetPolicy, apply_budget
from core.agent.degradation import degraded_result
from core.agent.execution import ExecutionBatch, dispatch_calls
from core.agent.handoff import HandoffChannel, handoff_tool
from core.agent.hooks.registry import NO_HOOKS, HookRegistry
from core.agent.message_queue import MessageQueue, merge
from core.agent.runtime_port import RunRequest, RunResult, RunStatus, SeedCall
from core.agent.seed_calls import EMPTY_SEED_CATALOGUE, SeedCatalogue
from core.agent.session import Session, SessionStatus
from core.agent.stagnation import final_turn_instruction, observe
from core.agent.store import SessionStore, save_quietly
from core.agent.subagents.definition import SubAgent
from core.agent.subagents.dispatch import (
    DISPATCH_CAPABILITY,
    SubAgentCatalogue,
    SubAgentDispatcher,
    SubAgentRun,
    SubAgentRunner,
    child_budget,
    dispatch_schema,
)
from core.agent.subagents.findings import finding_from_answer
from core.agent.tool_cache import ToolCallCache
from core.agent.turn import (
    BudgetAction,
    GuardrailAction,
    GuardrailActionKind,
    HookFailure,
    ToolExecution,
    Turn,
)
from core.capability.registered import RegisteredTool
from core.llm.probe import UNMEASURED_LIMITS, ModelLimits
from core.llm.routing import TaskClass
from core.llm.types import (
    InvokeRequest,
    InvokeResult,
    LLMClient,
    Message,
    Role,
    ToolCall,
    ToolSchema,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name the canonical runtime is recorded under. The benchmark guard reads
#: ``is_canonical`` rather than this, so renaming it cannot weaken the check.
CANONICAL_RUNTIME_NAME = "ninjasre.react"

#: Returned by ``run`` when a run is cancelled before it produced an answer.
CANCELLED_ANSWER = "Investigation cancelled before a conclusion was reached."

#: What a paused run reports while a person is driving it. Says resumable
#: explicitly, because the alternative reading — that the investigation stopped
#: — is what a takeover exists to avoid producing two records of.
PAUSED_ANSWER = (
    "Investigation suspended so a person could take it over. The evidence "
    "gathered so far is intact and the run is resumable."
)


class ReActLoop:
    """The first-party ReAct runtime.

    ``clock`` is injected so the wall-clock ceiling is testable without spending
    it. It is a monotonic source, not a wall time: a run must not become
    unbounded because somebody adjusted the system clock during it.
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        tools: Sequence[RegisteredTool] = (),
        subagents: Sequence[SubAgent] = (),
        subagent_runner: SubAgentRunner | None = None,
        seed_catalogue: SeedCatalogue = EMPTY_SEED_CATALOGUE,
        conclusion: ConclusionPolicy | None = None,
        hooks: HookRegistry = NO_HOOKS,
        handoff_channel: HandoffChannel | None = None,
        messages: MessageQueue | None = None,
        store: SessionStore | None = None,
        limits: ModelLimits = UNMEASURED_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        session_ids: Callable[[], str] | None = None,
    ) -> None:
        # The cap is on what a turn carries, so the two schemas the loop adds
        # for itself count against it. Checking only the selected capabilities
        # would let a run with a handoff channel and specialists configured send
        # two more schemas than Article II allows, on every turn.
        offered = len(tools) + (1 if handoff_channel is not None else 0) + (1 if subagents else 0)
        if offered > MAX_AGENT_TOOL_SCHEMAS:
            raise ValueError(
                f"a turn may carry at most {MAX_AGENT_TOOL_SCHEMAS} tool schemas, and this "
                f"loop would send {offered} ({len(tools)} selected capabilities, plus the "
                "handoff and sub-agent dispatch schemas it adds) — capability selection caps "
                "this before the loop sees it"
            )

        self._llm = llm
        self._tools = {registered.name: registered for registered in tools}
        if handoff_channel is not None:
            asking = handoff_tool(handoff_channel)
            self._tools[asking.name] = asking
        self._handoff_channel = handoff_channel
        self._messages = messages
        self._store = store
        # What this model was measured to be able to hold. The shipped ceilings
        # where nobody probed, so a deployment that never ran the probe behaves
        # exactly as it did before any of this existed.
        self._limits = limits
        self._seeds = seed_catalogue
        self._conclusion: ConclusionPolicy = conclusion or AcceptAnyAnswer()
        self._hooks = hooks
        self._clock = clock
        self._session_ids = session_ids or (lambda: f"run-{uuid.uuid4().hex[:12]}")
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()
        # Children by parent, so a takeover can reap what a run has in flight
        # without a second registry to keep in step with the dispatcher.
        self._children: dict[str, list[str]] = {}

        self._catalogue = SubAgentCatalogue(definitions=tuple(subagents))
        self._dispatcher = (
            SubAgentDispatcher(
                catalogue=self._catalogue,
                runner=subagent_runner or self._run_subagent,
                available=self.tools,
            )
            if self._catalogue
            else None
        )
        self._dispatched = 0

    # -- the port -------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the identifier this runtime is recorded under."""
        return CANONICAL_RUNTIME_NAME

    @property
    def is_canonical(self) -> bool:
        """Return ``True``: this is the runtime evaluation numbers come from."""
        return True

    @property
    def tools(self) -> tuple[RegisteredTool, ...]:
        """Return the capabilities this loop can call, in name order."""
        return tuple(self._tools[name] for name in sorted(self._tools))

    def new_session(self, request: RunRequest) -> Session:
        """Return the session ``request`` would run in, without running it.

        Exposed because a caller that wants to persist a session before the
        first model call, or seed it with evidence it already holds, cannot do
        either if the session only exists inside ``run``.
        """
        return Session(
            id=request.session_id or self._session_ids(),
            objective=request.objective,
            system_prompt=request.system_prompt or DEFAULT_RUNTIME_SYSTEM_PROMPT,
            alert_source=request.alert_source,
            context=dict(request.context),
            max_iterations=request.max_iterations,
            wall_clock_seconds=request.wall_clock_seconds,
            context_budget_tokens=request.context_budget_tokens,
        )

    async def run(self, request: RunRequest) -> RunResult:
        """Return the outcome of one investigation."""
        session = self.new_session(request)
        return await self._drive(session, seeds=self._seed_calls(session, request))

    async def resume(self, session: Session) -> RunResult:
        """Return the outcome of continuing ``session`` from where it stopped."""
        return await self._drive(session, seeds=())

    async def cancel(self, session_id: str) -> None:
        """Ask ``session_id`` to stop at its next safe point.

        Recorded rather than acted on. Tearing a run down mid-call would leave
        a tool result that happened and was never written anywhere, which is the
        one thing a resumable session cannot survive.
        """
        self._cancelled.add(session_id)

    async def pause(self, session_id: str) -> None:
        """Ask ``session_id`` to suspend at its next safe point, for a human.

        Distinct from ``cancel`` in the state it leaves behind and in nothing
        else about how it stops. A paused run is ``SUSPENDED`` and resumable
        with its evidence intact; a cancelled one is over. Both stop between
        iterations rather than mid-call, because a tool result that happened and
        was never written down is the one thing a resumable session cannot
        survive.
        """
        self._paused.add(session_id)

    def children_of(self, session_id: str) -> tuple[str, ...]:
        """Return the sub-agent sessions ``session_id`` has dispatched."""
        return tuple(self._children.get(session_id, ()))

    def share_control_with(self, parent: ReActLoop) -> None:
        """Adopt ``parent``'s stop signals, so cancelling it reaches this loop.

        A specialist runs in its own loop instance, which means the parent's
        ``cancel`` and ``pause`` sets are not the ones it checks. Sharing the
        sets rather than copying them is what makes reaping work: a takeover
        that stops the parent has to reach the sub-agent that is halfway
        through a call against the system the person is about to change.
        """
        self._cancelled = parent._cancelled  # noqa: SLF001 — one loop's own kind
        self._paused = parent._paused  # noqa: SLF001 — one loop's own kind
        self._children = parent._children  # noqa: SLF001 — one loop's own kind

    # -- seeds ----------------------------------------------------------------

    def _seed_calls(self, session: Session, request: RunRequest) -> tuple[SeedCall, ...]:
        """Return the deterministic calls to run before the first model turn."""
        return (*self._seeds.for_source(session.alert_source), *request.seed_calls)

    async def _run_seeds(
        self, session: Session, seeds: Sequence[SeedCall], cache: ToolCallCache
    ) -> tuple[ToolExecution, ...]:
        """Run the seed calls and fold their results into the transcript."""
        if not seeds:
            return ()

        calls = tuple(
            ToolCall(id=f"seed-{index}", name=seed.capability, arguments=dict(seed.arguments))
            for index, seed in enumerate(seeds, start=1)
        )
        session.append(Message(role=Role.ASSISTANT, tool_calls=calls))
        batch = await dispatch_calls(
            calls,
            tools=self._tools,
            session=session,
            cache=cache,
            iteration=0,
            result_chars=self._limits.tool_result_chars,
        )
        session.append(Message(role=Role.TOOL, tool_results=batch.tool_results))
        return batch.executions

    # -- driving --------------------------------------------------------------

    async def _drive(self, session: Session, *, seeds: Sequence[SeedCall]) -> RunResult:
        """Run iterations until the session reaches a terminal state."""
        deadline = self._clock() + session.wall_clock_seconds
        cache = ToolCallCache()
        policy = BudgetPolicy(total_tokens=session.context_budget_tokens)

        session.status = SessionStatus.RUNNING
        run_failures: list[HookFailure] = list(await self._hooks.run_run_start(session))

        if not session.transcript:
            session.append(Message(role=Role.USER, text=session.objective))
            await self._run_seeds(session, seeds, cache)

        while session.iteration < session.max_iterations:
            if session.id in self._cancelled:
                return await self._finish(self._cancelled_result(session), run_failures)

            # Checked after cancellation, because a run that is both cancelled
            # and paused is over: suspending it would leave a session somebody
            # is invited to resume when the decision to end it was already made.
            if session.id in self._paused:
                return await self._finish(self._paused_result(session), run_failures)

            pending = self._bounds_reached(session, deadline=deadline)
            outcome = await self._iterate(session, cache=cache, policy=policy, pending=pending)
            if outcome is not None:
                return await self._finish(outcome, run_failures)

        # Reached only if the ceiling arithmetic below ever stops holding. A
        # run that ends here has no answer, and saying so beats inventing one.
        return await self._finish(
            degraded_result(session, failure="the iteration ceiling was reached"), run_failures
        )

    async def _finish(self, result: RunResult, failures: list[HookFailure]) -> RunResult:
        """Dispatch the run-level hooks and attach whatever they broke on.

        ``on_cancel`` runs in addition to ``on_run_end`` rather than instead of
        it: a hook that persists state has to run whichever way the run ended,
        and one that reaps in-flight work only cares about the cancellation.
        """
        if result.status is RunStatus.CANCELLED:
            failures.extend(await self._hooks.run_cancel(result.session))
        failures.extend(await self._hooks.run_run_end(result.session, result))
        # Persisted after the hooks so a hook that touched the session — memory
        # finalisation, report delivery — is inside what gets written down.
        await save_quietly(self._store, result.session)
        return replace(result, hook_failures=tuple(failures))

    def _bounds_reached(self, session: Session, *, deadline: float) -> tuple[GuardrailAction, ...]:
        """Withdraw tool access when a run-level bound is spent, and say which."""
        if session.tools_stripped:
            return ()

        # One iteration is held back for the text-only turn, so a run that hits
        # the ceiling still answers from what it gathered rather than stopping
        # mid-thought.
        if session.iteration >= session.max_iterations - 1:
            return (
                self._strip_tools(
                    session,
                    GuardrailActionKind.ITERATION_CEILING_REACHED,
                    f"iteration {session.max_iterations} of "
                    f"{session.max_iterations} — answering from the evidence held",
                ),
            )

        if self._clock() >= deadline:
            return (
                self._strip_tools(
                    session,
                    GuardrailActionKind.WALL_CLOCK_EXCEEDED,
                    f"the {session.wall_clock_seconds:.0f}-second run ceiling was reached",
                ),
            )

        return ()

    def _strip_tools(
        self, session: Session, kind: GuardrailActionKind, reason: str
    ) -> GuardrailAction:
        """Withdraw tool access and tell the model, once."""
        session.tools_stripped = True
        session.append(Message(role=Role.USER, text=final_turn_instruction()))
        logger.info(
            "agent.tools_stripped",
            session_id=session.id,
            reason=kind.value,
            iteration=session.iteration,
        )
        return GuardrailAction(kind=kind, target=session.id, reason=reason)

    # -- one iteration --------------------------------------------------------

    def _offered_tools(self, guardrails: list[GuardrailAction]) -> tuple[RegisteredTool, ...]:
        """Return the capabilities this turn may carry, narrowed to the model's limit.

        The order the loop was constructed with is selection's ranking, so
        narrowing drops from the end of it rather than by name — dropping
        alphabetically would discard the capability selection thought was most
        relevant about a third of the time.

        This is a backstop rather than the mechanism. A composition root that
        knows the model's limits asks selection for that many capabilities in the
        first place, and then this never fires; when it does fire, it fires with
        a line in the trace saying so, because a turn that silently carried fewer
        capabilities than the run was configured with explains nothing.
        """
        held = tuple(self._tools.values())
        ceiling = min(self._limits.max_tool_schemas, MAX_AGENT_TOOL_SCHEMAS)
        if len(held) <= ceiling:
            return held

        dropped = tuple(registered.name for registered in held[ceiling:])
        guardrails.append(
            GuardrailAction(
                kind=GuardrailActionKind.SCHEMAS_NARROWED,
                target=", ".join(dropped),
                reason=(
                    f"the model holds at most {ceiling} tool schemas per turn; "
                    f"{len(held)} were selected and the lowest-ranked {len(dropped)} "
                    "were not offered"
                ),
            )
        )
        return held[:ceiling]

    def _schemas(
        self, session: Session, guardrails: list[GuardrailAction]
    ) -> tuple[ToolSchema, ...]:
        """Return the tool schemas this turn carries.

        Dispatch is offered as one more schema rather than as a registered
        capability: running it needs the session, the depth, and the runner, and
        none of those fit through a tool's signature. It is withdrawn with
        everything else on a text-only turn.
        """
        if session.tools_stripped:
            return ()

        offered = self._offered_tools(guardrails)
        schemas = [
            ToolSchema(
                name=registered.name,
                description=registered.metadata.description,
                parameters=registered.input_schema,
            )
            for registered in sorted(offered, key=lambda registered: registered.name)
        ]
        if self._dispatcher is not None and session.depth < self._dispatcher.max_depth:
            schemas.append(dispatch_schema(self._catalogue))
        return tuple(schemas)

    def _build_request(self, session: Session, guardrails: list[GuardrailAction]) -> InvokeRequest:
        """Return the provider-neutral request for this turn."""
        return InvokeRequest(
            messages=tuple(session.transcript),
            system=session.system_prompt or DEFAULT_RUNTIME_SYSTEM_PROMPT,
            tools=self._schemas(session, guardrails),
            parallel_tool_calls=True,
            metadata={"session_id": session.id, "iteration": str(session.iteration + 1)},
        )

    # -- mid-run input --------------------------------------------------------

    async def _merge_queued(self, session: Session, guardrails: list[GuardrailAction]) -> None:
        """Fold any queued guidance into the transcript as one numbered block.

        Merged at the turn boundary whether or not tool access is still open. A
        run on its final text-only turn still benefits from being told what the
        operator knows — and merging guidance does not give tools back, which is
        the property that makes this safe to do unconditionally.
        """
        if self._messages is None or not self._messages:
            return

        drained = await self._messages.drain()
        if not drained:
            return

        session.append(Message(role=Role.USER, text=merge(drained)))
        guardrails.append(
            GuardrailAction(
                kind=GuardrailActionKind.MESSAGE_QUEUED,
                target=session.id,
                reason=f"{len(drained)} queued message(s) merged at the turn boundary",
            )
        )
        # Acknowledged after the transcript already holds it. A receipt that
        # went out first would tell somebody the agent had read their message
        # in the window where a crash means it never did — and they would not
        # send it again, because they were told it landed.
        await self._messages.acknowledge(drained)
        logger.info("agent.message_queued", session_id=session.id, messages=len(drained))

    # -- sub-agents -----------------------------------------------------------

    async def _execute(
        self,
        calls: Sequence[ToolCall],
        *,
        session: Session,
        cache: ToolCallCache,
    ) -> ExecutionBatch:
        """Run one turn's calls, routing dispatches to the specialist runner.

        The two kinds run separately and the results are put back in the order
        the model asked. A model reading its own tool results out of order would
        reason from a sequence that never happened.
        """
        dispatches = [call for call in calls if call.name == DISPATCH_CAPABILITY]
        ordinary = [call for call in calls if call.name != DISPATCH_CAPABILITY]

        if dispatches and self._dispatcher is None:
            # No specialists configured, so the name is exactly as unknown as
            # any other capability the model invented.
            ordinary = list(calls)
            dispatches = []

        batches = [
            await dispatch_calls(
                ordinary,
                tools=self._tools,
                session=session,
                cache=cache,
                iteration=session.iteration,
                hooks=self._hooks,
                result_chars=self._limits.tool_result_chars,
            )
        ]
        if dispatches and self._dispatcher is not None:
            batches.append(
                await self._dispatcher.dispatch(
                    dispatches, session=session, cache=cache, iteration=session.iteration
                )
            )

        by_call = {
            outcome.execution.call_id: outcome for batch in batches for outcome in batch.outcomes
        }
        return ExecutionBatch(
            outcomes=tuple(by_call[call.id] for call in calls if call.id in by_call),
            guardrail_actions=tuple(
                action for batch in batches for action in batch.guardrail_actions
            ),
            hook_failures=tuple(failure for batch in batches for failure in batch.hook_failures),
        )

    async def _run_subagent(self, definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        """Run one specialist in its own session and return what it found.

        The child session carries the task and nothing else. That is the whole
        isolation guarantee, and it is a property of building a fresh
        ``Session`` rather than a rule the dispatcher has to keep following.
        """
        self._dispatched += 1
        child = Session(
            id=f"{parent.id}/{definition.name}-{self._dispatched}",
            objective=task,
            system_prompt=SUBAGENT_SYSTEM_PROMPT.format(
                name=definition.name, description=definition.description
            ),
            alert_source=parent.alert_source,
            depth=parent.depth + 1,
            parent_id=parent.id,
            subagent=definition.name,
            max_iterations=definition.max_iterations,
            wall_clock_seconds=parent.wall_clock_seconds,
            context_budget_tokens=child_budget(parent, definition),
        )
        # Recorded before the specialist starts, so a takeover arriving while it
        # is mid-flight finds it. Recorded after would leave exactly the window
        # a reaper exists to close.
        self._children.setdefault(parent.id, []).append(child.id)

        specialist = ReActLoop(
            llm=self._llm,
            tools=definition.subset(self.tools),
            subagents=self._catalogue.definitions,
            seed_catalogue=EMPTY_SEED_CATALOGUE,
            hooks=self._hooks,
            limits=self._limits,
            clock=self._clock,
        )
        specialist.share_control_with(self)
        result = await specialist.resume(child)

        return SubAgentRun(
            finding=finding_from_answer(definition.name, result.answer, child.evidence),
            session=child,
            guardrail_actions=tuple(
                action for turn in child.turns for action in turn.guardrail_actions
            ),
        )

    async def _iterate(
        self,
        session: Session,
        *,
        cache: ToolCallCache,
        policy: BudgetPolicy,
        pending: Sequence[GuardrailAction],
    ) -> RunResult | None:
        """Run one iteration. Returns a result only when the run is over."""
        session.iteration += 1
        started_at = datetime.now(UTC)
        started = self._clock()

        guardrails: list[GuardrailAction] = list(pending)
        hook_failures: list[HookFailure] = []

        # Order matters and is not arbitrary. Queued guidance is merged first
        # so it is in the transcript compaction will summarise around; the
        # budget runs last so it measures what is actually about to be sent.
        await self._merge_queued(session, guardrails)
        compaction = apply_compaction(
            session, usable_context_tokens=self._limits.usable_context_tokens
        )
        if compaction.compacted:
            guardrails.append(
                GuardrailAction(
                    kind=GuardrailActionKind.TRANSCRIPT_COMPACTED,
                    target=session.id,
                    reason=compaction.reason,
                )
            )
        budget_actions: tuple[BudgetAction, ...] = apply_budget(session, policy)

        request = self._build_request(session, guardrails)
        offered = tuple(schema.name for schema in request.tools)

        def record(executions: tuple[ToolExecution, ...]) -> Turn:
            return self._turn(
                session,
                started_at=started_at,
                started=started,
                offered=offered,
                result=result,
                executions=executions,
                budget_actions=budget_actions,
                guardrails=guardrails,
                hook_failures=hook_failures,
            )

        result = await self._llm.invoke(request)

        # Recorded whether or not the turn succeeded: a run that ended because a
        # model became unavailable is one where knowing which model it was is the
        # first thing anybody asks.
        session.attribute(
            TaskClass.REASONING,
            provider_id=result.provider_id,
            model_id=result.model_id,
            output=f"turn {session.iteration}",
        )

        if not result.succeeded:
            await self._record(session, record(()))
            logger.warning(
                "agent.model_unavailable",
                session_id=session.id,
                iteration=session.iteration,
                failure=result.failure.value if result.failure else "unknown",
            )
            return degraded_result(session, failure=result.failure_message)

        # A repaired call is not a clean call. Surfacing the repairs here is what
        # makes "this model costs you three attempts a turn" something an
        # operator can read off a run rather than infer from its wall clock.
        guardrails.extend(
            GuardrailAction(
                kind=GuardrailActionKind.MODEL_OUTPUT_REPAIRED,
                target=repair.capability or repair.kind.value,
                reason=f"{repair.kind.value}: {repair.detail}",
            )
            for repair in result.repairs
        )

        # A turn that carries no tool schemas may still come back with tool
        # calls: a provider replaying a cached response, a local model that
        # ignores the empty tool list, an adapter with a bug. Executing them
        # would give back the access the guardrail just withdrew, so they are
        # discarded and the text is taken as the answer.
        requested = () if session.tools_stripped else result.tool_calls
        if session.tools_stripped and result.tool_calls:
            guardrails.append(
                GuardrailAction(
                    kind=GuardrailActionKind.UNKNOWN_CAPABILITY,
                    target=", ".join(sorted({call.name for call in result.tool_calls})),
                    reason="tool access was withdrawn for this turn; the calls were discarded",
                )
            )

        session.append(Message(role=Role.ASSISTANT, text=result.text, tool_calls=requested))

        if requested:
            batch = await self._execute(requested, session=session, cache=cache)
            session.append(Message(role=Role.TOOL, tool_results=batch.tool_results))
            executions = batch.executions
            guardrails.extend(batch.guardrail_actions)
            hook_failures.extend(batch.hook_failures)
        else:
            executions = ()
            refusal = self._conclusion_refusal(session, result.text)
            if refusal is None:
                session.status = SessionStatus.COMPLETED
                await self._record(session, record(()))
                return RunResult(session=session, status=RunStatus.COMPLETED, answer=result.text)
            session.append(Message(role=Role.USER, text=refusal))

        # Stagnation is decided before the turn is written down, so the nudge
        # and the tool-access withdrawal appear on the iteration that caused
        # them rather than on the next one.
        self._apply_stagnation(
            session,
            produced_fresh_evidence=any(
                execution.produced_fresh_evidence for execution in executions
            ),
            guardrails=guardrails,
        )
        await self._record(session, record(executions))
        return None

    async def _record(self, session: Session, turn: Turn) -> None:
        """Store one turn and dispatch ``on_turn_end``.

        The hook receives the turn as an argument and the session without it:
        a hook that fails is recorded on the turn it failed during, which means
        the turn cannot already be in the transcript when the hook runs.
        """
        failures = await self._hooks.run_turn_end(session, turn)
        if failures:
            turn = replace(turn, hook_failures=(*turn.hook_failures, *failures))
        session.record_turn(turn)

    def _conclusion_refusal(self, session: Session, answer: str) -> str | None:
        """Return why an answer is not accepted, or ``None`` when it is.

        A run whose tools have already been withdrawn is never refused: the
        model has nothing left to call, so refusing would spend the remaining
        iterations asking for evidence that cannot be gathered.
        """
        if session.tools_stripped:
            return None
        acceptance = self._conclusion.accepts(session, answer)
        return None if acceptance.accepted else acceptance.reason

    def _apply_stagnation(
        self,
        session: Session,
        *,
        produced_fresh_evidence: bool,
        guardrails: list[GuardrailAction],
    ) -> None:
        """Count a sterile iteration and, at the threshold, withdraw tool access."""
        if session.tools_stripped:
            return

        verdict = observe(
            session.stagnant_iterations,
            produced_fresh_evidence=produced_fresh_evidence,
        )
        session.stagnant_iterations = verdict.count
        if not verdict.stagnant:
            return

        guardrails.append(
            GuardrailAction(
                kind=GuardrailActionKind.STAGNATION_NUDGE,
                target=session.id,
                reason=f"iteration {session.iteration} produced no new evidence",
            )
        )
        session.append(Message(role=Role.USER, text=verdict.nudge))

        if verdict.strip_tools:
            guardrails.append(
                self._strip_tools(
                    session,
                    GuardrailActionKind.TOOL_ACCESS_STRIPPED,
                    f"{verdict.count} consecutive iterations produced no new evidence",
                )
            )

    def _turn(
        self,
        session: Session,
        *,
        started_at: datetime,
        started: float,
        offered: tuple[str, ...],
        result: InvokeResult,
        executions: tuple[ToolExecution, ...],
        budget_actions: tuple[BudgetAction, ...],
        guardrails: Sequence[GuardrailAction],
        hook_failures: Sequence[HookFailure] = (),
    ) -> Turn:
        """Return the trace record for one iteration."""
        return Turn(
            index=session.iteration,
            started_at=started_at,
            duration_seconds=self._clock() - started,
            offered_capabilities=offered,
            rationale=result.text,
            provider_id=result.provider_id,
            model_id=result.model_id,
            finish_reason=result.finish_reason,
            executions=executions,
            usage=result.usage,
            budget_actions=budget_actions,
            guardrail_actions=tuple(guardrails),
            hook_failures=tuple(hook_failures),
        )

    def _cancelled_result(self, session: Session) -> RunResult:
        """Return the result for a run stopped at a safe point."""
        session.status = SessionStatus.CANCELLED
        session.touch()
        logger.info("agent.cancelled", session_id=session.id, iteration=session.iteration)
        return RunResult(session=session, status=RunStatus.CANCELLED, answer=CANCELLED_ANSWER)

    def _paused_result(self, session: Session) -> RunResult:
        """Return the result for a run suspended so a person can drive it.

        ``PARTIAL`` rather than ``CANCELLED``: what the run gathered is intact
        and the investigation is not over, which is the same shape as a run the
        model went unavailable during. The session status is what says the
        difference, and it is what a resumption reads.
        """
        session.status = SessionStatus.SUSPENDED
        session.touch()
        self._paused.discard(session.id)
        logger.info("agent.paused", session_id=session.id, iteration=session.iteration)
        return RunResult(session=session, status=RunStatus.PARTIAL, answer=PAUSED_ANSWER)


__all__ = [
    "CANCELLED_ANSWER",
    "CANONICAL_RUNTIME_NAME",
    "PAUSED_ANSWER",
    "ReActLoop",
]
