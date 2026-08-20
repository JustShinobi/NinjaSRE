"""Driving the canonical loop from the eight-method contract the routes hold.

``ReActInvestigationRunner`` is the first implementation of
``gateway.http.services.InvestigationRunner`` this repository ships — every
deployment before this feature ran ``UnconfiguredInvestigator``, whichever
factory it named. It composes exactly one runtime per investigation:
``core.agent.react_loop.ReActLoop``, the loop Article V reserves for
published numbers. Built fresh for each call, because the model's tool-schema
ceiling is smaller than the declared capability catalogue and which tools are
worth offering depends on what the alert is about — narrowing has to happen
before the loop is constructed, not after, since the loop's own constructor
refuses to be built beyond that ceiling.

Steering a running investigation — cancelling it, taking it over, queuing a
message, resuming it — is served against the same loop instance, tracked in
memory for the run's identity. Interactions (the loop asking a human a
question mid-run) are not served here: nothing in this composition binds the
``ask_human`` desk, so a run that reaches for it finds nobody to ask, which is
that capability's own supported "unavailable" outcome rather than a crash.
Wiring a desk, and round-tripping a resumed run's eventual outcome back to
the run-trace store, are later work — named in this feature's report rather
than hidden here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from capabilities.registry.catalogue import Registry
from capabilities.registry.planning import CatalogueRanker
from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from core.agent.interaction.models import Interaction
from core.agent.message_queue import MessageQueue
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session
from core.capability.registered import RegisteredTool
from core.llm.types import LLMClient
from core.pipeline.build import investigation_hooks
from core.pipeline.ports import IncidentSignals
from gateway.http.services import InvestigationStart


class InvestigationDidNotComplete(RuntimeError):
    """The canonical loop ran and produced no usable answer.

    Raised by ``investigate`` rather than returned, so the caller
    (``gateway.http.orchestration._drive``) records the run as failed instead
    of completed. A degraded (``PARTIAL``) result is not this: it is still
    returned normally, because the investigation did complete, on less
    evidence than it asked for.
    """


class NoPendingInteraction(RuntimeError):
    """No interaction is waiting to be answered.

    This composition does not bind a desk for the agent to put a mid-run
    question to a human (see the module docstring), so nothing is ever
    pending — this is the honest answer to a caller that tries to close one
    anyway, rather than a silent success that closed nothing.
    """


@dataclass(slots=True)
class _LiveRun:
    """What this process remembers about one investigation while it can act on it."""

    loop: ReActLoop
    messages: MessageQueue
    #: Set once the loop returns having been taken over — the session a later
    #: ``resume`` hands back to the agent. ``None`` the rest of the time,
    #: including after a normal completion: there is nothing left to resume.
    session: Session | None = None


@dataclass(slots=True)
class ReActInvestigationRunner:
    """Composes ``ReActLoop`` per investigation and steers it by run id.

    ``llm`` and ``registry`` are supplied once, by the factory that builds
    this object; everything that varies per investigation — which tools are
    offered, the session identity, mid-run messages — is built inside
    ``investigate``.
    """

    llm: LLMClient
    registry: Registry
    _live: dict[str, _LiveRun] = field(default_factory=dict)

    async def investigate(self, request: InvestigationStart) -> str:
        """Run the investigation to completion and return its summary.

        Raises :class:`InvestigationDidNotComplete` when the loop's own
        outcome is ``FAILED`` — the loop ran and produced nothing usable — so
        the caller records the run as failed rather than completed.
        """
        queue = MessageQueue(run_id=request.run_id)
        loop = self._build_runtime(request, messages=queue)
        live = _LiveRun(loop=loop, messages=queue)
        self._live[request.run_id] = live

        result = await loop.run(self._request_of(request))

        if result.status is RunStatus.FAILED:
            raise InvestigationDidNotComplete(
                result.failure or "the investigation produced no answer"
            )
        return result.answer or f"investigation ended {result.status.value}"

    async def cancel(self, run_id: str) -> None:
        """Ask ``run_id`` to stop at its next safe point.

        A no-op when ``run_id`` names nothing this process is driving — there
        is nothing to ask.
        """
        live = self._live.get(run_id)
        if live is not None:
            await live.loop.cancel(run_id)

    async def take_over(self, run_id: str, *, principal: str) -> None:
        """Suspend ``run_id`` at its next safe point so ``principal`` can drive it.

        Uses the loop's own ``pause``: the run keeps its session and evidence
        intact and stops between iterations, exactly as the protocol
        promises, and the session it stopped with is kept so a later
        ``resume`` can hand it back. What this does not do is reap in-flight
        sub-agents or record a human action against the run's trace —
        ``core.agent.takeover.Takeover`` exists for that and is not wired
        into this composition (see the module docstring and this slice's
        report).
        """
        live = self._live.get(run_id)
        if live is None:
            return
        await live.loop.pause(run_id)

    async def resume(self, run_id: str) -> None:
        """Hand ``run_id`` back to the agent from wherever it paused.

        A no-op unless a take-over left a session behind. The resumed run is
        driven to completion here and this returns once it does, matching the
        protocol's ``-> None``; nothing records its eventual outcome back to
        the run-trace store — an existing gap in how resume is wired end to
        end (see the report), not one this method can close on its own since
        it is never handed the store.
        """
        live = self._live.get(run_id)
        if live is None or live.session is None:
            return
        session = live.session
        live.session = None
        await live.loop.resume(session)

    async def queue_message(self, run_id: str, text: str) -> None:
        """Queue ``text`` for delivery on the run's next turn.

        A no-op when ``run_id`` names nothing this process is driving — there
        is no turn boundary left to deliver it at.
        """
        live = self._live.get(run_id)
        if live is not None:
            live.messages.submit(text, author="operator")

    async def pending_interactions(self, run_id: str) -> tuple[Interaction, ...]:
        """Return no interactions: this composition raises none to answer."""
        return ()

    async def find_interaction(self, interaction_id: str) -> Interaction | None:
        """Return ``None``: no interaction desk is bound in this composition."""
        return None

    async def answer_interaction(
        self,
        interaction_id: str,
        *,
        text: str,
        principal: str,
        selected_option: str = "",
    ) -> Interaction:
        """Raise: nothing is ever pending, so nothing can be closed."""
        raise NoPendingInteraction(
            f"no interaction {interaction_id!r} is pending — this composition "
            "does not put a mid-run question to a human"
        )

    # -- composition ------------------------------------------------------

    def _build_runtime(self, request: InvestigationStart, *, messages: MessageQueue) -> ReActLoop:
        """Return the canonical loop, carrying at most the tools the model may hold."""
        return ReActLoop(
            llm=self.llm,
            tools=self._select_tools(request),
            hooks=investigation_hooks(),
            messages=messages,
        )

    def _select_tools(self, request: InvestigationStart) -> tuple[RegisteredTool, ...]:
        """Return the tools this investigation may call, ranked and capped.

        The registry declares more capabilities than ``MAX_AGENT_TOOL_SCHEMAS``
        allows on one turn, so a subset has to be chosen before the loop is
        built. Chosen by the same deterministic ranker the investigation
        pipeline uses elsewhere, scored against what this alert says about
        itself — not against which integrations a team has configured, which
        this composition has no way to ask without a database handle a
        no-argument factory does not hold (see the report). A capability this
        deployment has no credential for is still offered; it reports itself
        unavailable by name when called, which is the credential proxy
        binding's own designed outcome for exactly that case.
        """
        declarations = tuple(tool.metadata for tool in self.registry.tools.values())
        signals = IncidentSignals(alert_source=request.alert_source, summary=request.objective)
        ranked = CatalogueRanker().rank(declarations, signals)

        selected: list[RegisteredTool] = []
        for entry in ranked:
            if len(selected) >= MAX_AGENT_TOOL_SCHEMAS:
                break
            found = self.registry.tool(entry.name)
            if found is not None:
                selected.append(found)
        return tuple(selected)

    def _request_of(self, request: InvestigationStart) -> RunRequest:
        """Return the loop's own view of this investigation.

        ``session_id`` is the incident's run id, unchanged, so a later
        ``cancel``/``take_over``/``queue_message`` naming the same run id
        reaches the session this loop is actually driving. Every bound —
        iteration ceiling, wall clock, context budget — is left at
        ``RunRequest``'s own default, which is Article II's ceiling: this
        composition lowers nothing and raises nothing.
        """
        return RunRequest(
            objective=request.objective,
            alert_source=request.alert_source,
            session_id=request.run_id,
            context=dict(request.context),
        )


__all__ = [
    "InvestigationDidNotComplete",
    "NoPendingInteraction",
    "ReActInvestigationRunner",
]
