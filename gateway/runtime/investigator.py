"""Driving the canonical loop from the eight-method contract the routes hold.

``ReActInvestigationRunner`` is the first implementation of
``gateway.http.services.InvestigationRunner`` this repository ships — every
deployment before this feature ran ``UnconfiguredInvestigator``, whichever
factory it named. It composes exactly one runtime per investigation:
``core.agent.react_loop.ReActLoop``, the canonical loop. Built fresh for each
call, because the model's tool-schema ceiling is smaller than the declared
capability catalogue and which tools are worth offering depends on what the
alert is about and on what this deployment can carry out — narrowing has to
happen before the loop is constructed, not after, since the loop's own
constructor refuses to be built beyond that ceiling.

Three things are built per investigation and never per process, and the reason
is the same for all three: they carry the identity of one run.

**The remediation gate**, when this deployment composed a desk. Its run context
names who asked and for which team, so a gate shared between runs would propose
changes attributed to whoever happened to build it.

**The question desk**, so a person answering on one incident cannot close the
question another incident raised. That is the failure a process-wide binding
produces and the one nobody would notice.

**The tool selection**, narrowed twice — by the integrations the team has
connected and by whether this deployment could carry a write out at all — and
only then ranked and cut at the ceiling. Cutting first spends slots of a small
budget on capabilities that were about to be removed.

Steering a running investigation — cancelling it, taking it over, queuing a
message, resuming it — is served against the same loop instance, tracked in
memory for the run's identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from capabilities.registry.catalogue import Registry
from capabilities.registry.planning import CatalogueRanker, TeamCatalogueResolver
from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from core.agent.handoff import HANDOFF_CAPABILITY, HumanHandoff
from core.agent.interaction.models import Interaction
from core.agent.interaction.registry import InteractionRegistry
from core.agent.message_queue import MessageQueue
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session
from core.capability.metadata import CapabilityKind, ExcludedCapability
from core.capability.ports import ConfiguredIntegrations, IntegrationAvailability
from core.capability.registered import RegisteredTool
from core.llm.types import LLMClient
from core.pipeline.build import investigation_hooks
from core.pipeline.ports import IncidentSignals
from core.pipeline.stages.resolve_integrations import zero_integration_outcome
from core.state.catalogue import ResolvedCapabilities
from core.state.types import InvestigationOutcome
from gateway.http.services import InvestigationStart
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.remediation.gating import RunContext
from platform.runs.recording import RunTraceRecordingHook
from platform.runs.stream import RunEventBroker
from platform.sandbox.selection import resolve_profile

logger = get_logger(__name__)

#: Which argument of the alert's context names the environment a write would
#: land in. Read from the request rather than from the process, because one
#: deployment investigates more than one environment.
ENVIRONMENT_KEY = "environment"


class InvestigationDidNotComplete(RuntimeError):
    """The canonical loop ran and produced no usable answer.

    Raised by ``investigate`` rather than returned, so the caller
    (``gateway.http.orchestration._drive``) records the run as failed instead
    of completed. A degraded (``PARTIAL``) result is not this: it is still
    returned normally, because the investigation did complete, on less
    evidence than it asked for.
    """


class NoPendingInteraction(RuntimeError):
    """No interaction with that identifier was raised by any run here.

    Deliberately distinct from an interaction that exists and has already been
    answered. A surface that arrived second has to tell its human who did
    answer, and one that named something nobody raised has to be told that
    instead — collapsing the two sends somebody looking for a question that was
    never asked.
    """


@dataclass(slots=True)
class _LiveRun:
    """What this process remembers about one investigation while it can act on it."""

    loop: ReActLoop
    messages: MessageQueue
    #: Where this run's questions live. One desk per run: an answer given on one
    #: incident must not close the question another incident raised.
    handoff: HumanHandoff | None = None
    #: Set once the loop returns having been taken over — the session a later
    #: ``resume`` hands back to the agent. ``None`` the rest of the time,
    #: including after a normal completion: there is nothing left to resume.
    session: Session | None = None


@dataclass(frozen=True, slots=True)
class _RecordingComposition:
    """What ``attach_recording`` gives a runner to write through.

    Held as one small value rather than three loose fields so a single
    ``is None`` check on ``ReActInvestigationRunner._recording`` answers
    "can this runner record" for every collaborator at once.
    """

    gateway: PersistenceGateway
    guardrails: GuardrailEngine
    broker: RunEventBroker


async def team_availability(
    gateway: PersistenceGateway, *, org_id: str, team_node_id: str
) -> IntegrationAvailability:
    """Return what the team on this run has connected, from the configuration tree.

    The same list the catalogue view reads to say how many capabilities a team
    has and how many are waiting on an integration. One source, so what a screen
    counts and what an investigation is handed cannot disagree.
    """
    scope = TenantScope(org_id=org_id, team_node_id=team_node_id or None)
    effective = await ConfigService(gateway=gateway, scope=scope).resolve(team_node_id or org_id)
    return ConfiguredIntegrations(
        integrations=tuple(effective.config.integrations.enabled_names()),
        # A sandbox profile is a property of the deployment rather than of the
        # team: a capability that needs one needs the one this process runs.
        sandbox_profiles=(resolve_profile().value,),
    )


@dataclass(slots=True)
class ReActInvestigationRunner:
    """Composes ``ReActLoop`` per investigation and steers it by run id.

    ``llm`` and ``registry`` are supplied once, by the factory that builds
    this object; everything that varies per investigation — which tools are
    offered, the session identity, mid-run messages, the gate, the question
    desk — is built inside ``investigate``.

    Recording and the remediation desk are both attached after construction,
    for the same reason: a tenant-scoped persistence handle and a composed
    executor are not things a no-argument factory holds. A runner nobody
    attached either to writes nothing and proposes nothing, and behaves exactly
    as it did before — composed nothing is still a valid, working deployment.
    """

    llm: LLMClient
    registry: Registry
    _live: dict[str, _LiveRun] = field(default_factory=dict)
    _recording: _RecordingComposition | None = field(default=None, repr=False)
    _remediation: Any = field(default=None, repr=False)

    def attach_recording(
        self, *, gateway: PersistenceGateway, guardrails: GuardrailEngine, broker: RunEventBroker
    ) -> None:
        """Give this runner somewhere to write what every investigation does.

        Called once, by the composition root that built this runner
        (``gateway.http.asgi.investigator_of``) — never by ``investigate``
        itself, which has no store of its own to reach for.
        """
        self._recording = _RecordingComposition(
            gateway=gateway, guardrails=guardrails, broker=broker
        )

    def attach_remediation(self, desk: Any) -> None:
        """Give this runner the desk a proposed write travels through.

        Called once, by the asynchronous composition root, and after that root
        has rebuilt the runner — the desk installed on a runner that is then
        replaced is a desk the loop never sees.
        """
        self._remediation = desk

    @property
    def can_record(self) -> bool:
        """Return whether this runner has somewhere to write what it does."""
        return self._recording is not None

    @property
    def remediation(self) -> Any:
        """Return the composed remediation desk, or ``None`` when there is none."""
        return self._remediation

    async def investigate(self, request: InvestigationStart) -> str:
        """Run the investigation to completion and return its summary.

        Raises :class:`InvestigationDidNotComplete` when the loop's own
        outcome is ``FAILED`` — the loop ran and produced nothing usable — so
        the caller records the run as failed rather than completed. A
        ``PARTIAL`` outcome is not this: it is a real completion on less
        evidence than the loop asked for, and is reported here with the
        product's own canonical word for that state — "degraded" — rather
        than as a summary a reader would have to infer the state from.

        A run whose team can execute nothing at all ends before the model is
        called, with the answer that names what to connect. Spending the run's
        only model call on its cheapest sentence would be spending it on
        nothing.
        """
        queue = MessageQueue(run_id=request.run_id)
        handoff = self._handoff_for(request)
        selection = await self._select_tools(request, handoff=handoff)

        if selection.outcome is not None:
            return _outcome_summary(selection.outcome)

        loop = self._build_runtime(request, messages=queue, tools=selection.tools)
        live = _LiveRun(loop=loop, messages=queue, handoff=handoff)
        self._live[request.run_id] = live

        result = await loop.run(self._request_of(request))

        if result.status is RunStatus.FAILED:
            raise InvestigationDidNotComplete(
                result.failure or "the investigation produced no answer"
            )
        if result.degraded:
            return _degraded_summary(result.answer)
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
        into this composition (see this slice's report).
        """
        del principal  # the loop pauses the run; who asked is the trace's business
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
        """Return the open questions ``run_id`` raised, longest-waiting first."""
        live = self._live.get(run_id)
        if live is None or live.handoff is None:
            return ()
        return live.handoff.registry.pending

    async def find_interaction(self, interaction_id: str) -> Interaction | None:
        """Return one interaction wherever it was raised, or ``None``.

        Searched across the runs this process is driving rather than in one,
        because the route that reads this holds an interaction identifier and
        is about to check which team the run behind it belongs to.
        """
        desk = self._desk_holding(interaction_id)
        return None if desk is None else desk.registry.find(interaction_id)

    async def answer_interaction(
        self,
        interaction_id: str,
        *,
        text: str,
        principal: str,
        selected_option: str = "",
    ) -> Interaction:
        """Close ``interaction_id`` with this answer, and wake the run waiting on it.

        The first answer wins. A second one is handed back the interaction as
        the first answer left it, so the surface that arrived late can say who
        answered and with what rather than only that it was too late — the run
        has already acted on what it was told, and rewriting the record would
        make the trace describe a run that did not happen.
        """
        desk = self._desk_holding(interaction_id)
        if desk is None:
            raise NoPendingInteraction(
                f"no interaction {interaction_id!r} was raised by any run this process is driving"
            )
        resolution = await desk.answer(
            interaction_id, text=text, principal=principal, selected_option=selected_option
        )
        return resolution.interaction

    # -- composition ------------------------------------------------------

    def _desk_holding(self, interaction_id: str) -> HumanHandoff | None:
        """Return the desk of the run that raised ``interaction_id``, if any."""
        for live in self._live.values():
            if live.handoff is not None and live.handoff.registry.find(interaction_id) is not None:
                return live.handoff
        return None

    def _handoff_for(self, request: InvestigationStart) -> HumanHandoff:
        """Return this investigation's own desk, with its own interaction registry."""
        return HumanHandoff(
            registry=InteractionRegistry(run_id=request.run_id),
            run_id=request.run_id,
            surfaces=(request.principal_id,) if request.principal_id else (),
        )

    def _run_context(self, request: InvestigationStart) -> RunContext:
        """Return who this run acts for, bound once rather than read per call."""
        return RunContext(
            requester=request.principal_id,
            team_node_id=request.team_node_id or None,
            run_id=request.run_id,
            environment=str(request.context.get(ENVIRONMENT_KEY, "")),
        )

    def _build_runtime(
        self,
        request: InvestigationStart,
        *,
        messages: MessageQueue,
        tools: tuple[RegisteredTool, ...],
    ) -> ReActLoop:
        """Return the canonical loop, carrying at most the tools the model may hold."""
        hooks = investigation_hooks(recorder=self._recording_hook_for(request))
        if self._remediation is not None:
            # Registered at ``pre_tool_use`` after the guardrails and before
            # anything else, carrying this run's own context. It is the point
            # that decides whether a tool call may happen at all, which is why
            # a write cannot reach a capability body by any other route.
            self._remediation.gate_for(self._run_context(request)).register(hooks)
        return ReActLoop(llm=self.llm, tools=tools, hooks=hooks, messages=messages)

    def _recording_hook_for(self, request: InvestigationStart) -> RunTraceRecordingHook | None:
        """Return this investigation's own recording hook, or ``None`` when unattached.

        A fresh hook per investigation, scoped to this run's own tenant and
        identity — the same "one instance per investigation" shape
        ``_LiveRun`` already keeps for the loop it drives.
        """
        if self._recording is None:
            return None
        return RunTraceRecordingHook(
            gateway=self._recording.gateway,
            scope=TenantScope(org_id=request.org_id, team_node_id=request.team_node_id),
            run_id=request.run_id,
            guardrails=self._recording.guardrails,
            broker=self._recording.broker,
        )

    async def _select_tools(
        self, request: InvestigationStart, *, handoff: HumanHandoff
    ) -> _Selection:
        """Return the tools this investigation may call, narrowed, ranked and capped.

        Four steps, and the order is the specification.

        First, narrow to what this team has connected. A capability needing an
        integration nobody configured reports itself unavailable by name when
        called, which costs the turn either way.

        Second, narrow to what this deployment could carry out. A write is
        offered only when a remediation desk is composed *and* the components
        for that capability are registered; without both it would come back as
        a refusal, and a wasted slot in a small budget is a reading the
        investigation did not do.

        Third, hand the question over to this run's own desk, by name, so the
        process-wide binding is not the one the model reaches.

        Only then rank against what the alert says and cut at the ceiling.
        Cutting earlier would spend the budget on capabilities that were about
        to be removed.
        """
        catalogue = TeamCatalogueResolver(self.registry).for_availability(
            await self._availability(request)
        )
        carriable = tuple(found for found in catalogue.tools if self._can_carry(found))
        excluded = catalogue.excluded + tuple(
            _uncarried(found) for found in catalogue.tools if not self._can_carry(found)
        )

        if not carriable:
            resolved = ResolvedCapabilities.of(
                catalogue.tools, catalogue.metadata(), tuple(excluded)
            )
            return _Selection(
                tools=(),
                outcome=zero_integration_outcome(resolved, alert_source=request.alert_source),
            )

        offered = {found.name: found for found in carriable}
        if HANDOFF_CAPABILITY in offered:
            offered[HANDOFF_CAPABILITY] = handoff.tool()

        signals = IncidentSignals(alert_source=request.alert_source, summary=request.objective)
        ranked = CatalogueRanker().rank(
            tuple(found.metadata for found in offered.values()), signals
        )

        selected: list[RegisteredTool] = []
        for entry in ranked:
            if len(selected) >= MAX_AGENT_TOOL_SCHEMAS:
                break
            found = offered.get(entry.name)
            if found is not None:
                selected.append(found)
        return _Selection(tools=tuple(selected), outcome=None)

    async def _availability(self, request: InvestigationStart) -> IntegrationAvailability:
        """Return what this run's team has, reading silence as the strictest posture.

        A configuration that could not be read must not become permission. The
        run continues with nothing connected — which produces the answer naming
        what to connect — and the reason goes into the log rather than being
        swallowed.
        """
        if self._recording is None:
            # No persistence handle, so there is no configuration tree to ask.
            # That is not the same fact as "this team has connected nothing",
            # and reading it as the strict one would leave a deployment that
            # composed no store able to run nothing at all — a behaviour change
            # for every caller that composed nothing, which is meant to behave
            # exactly as it did.
            return _EVERYTHING_AVAILABLE
        try:
            return await team_availability(
                self._recording.gateway,
                org_id=request.org_id,
                team_node_id=request.team_node_id,
            )
        except Exception as unreadable:  # noqa: BLE001 — an unread configuration is not permission
            logger.warning(
                "investigation.team_configuration_unreadable",
                run_id=request.run_id,
                team_node_id=request.team_node_id,
                error=str(unreadable),
            )
            return ConfiguredIntegrations(sandbox_profiles=(resolve_profile().value,))

    def _can_carry(self, found: RegisteredTool) -> bool:
        """Return whether this deployment could take ``found`` through to an effect."""
        if not found.metadata.side_effect_level.needs_approval:
            return True
        desk = self._remediation
        return desk is not None and bool(desk.handles(found.name))

    def _request_of(self, request: InvestigationStart) -> RunRequest:
        """Return the loop's own view of this investigation.

        ``session_id`` is the incident's run id, unchanged, so a later
        ``cancel``/``take_over``/``queue_message`` naming the same run id
        reaches the session this loop is actually driving. Every bound —
        iteration ceiling, wall clock, context budget — is left at
        ``RunRequest``'s own default: this composition lowers nothing and
        raises nothing.
        """
        return RunRequest(
            objective=request.objective,
            alert_source=request.alert_source,
            session_id=request.run_id,
            context=dict(request.context),
        )


@dataclass(frozen=True, slots=True)
class _NothingNarrows:
    """Availability for a runner with no configuration tree to consult.

    Says yes to everything, which is what the selection did before a team
    narrowing existed. A runner with no persistence handle cannot ask which
    integrations a team has; answering "none" would be inventing a reading
    rather than admitting there is none.
    """

    def is_available(self, name: str) -> bool:
        """Return ``True``: nothing here knows enough to exclude anything."""
        del name
        return True

    def unmet(self, requirements: Any) -> tuple[str, ...]:
        """Return no unmet requirements."""
        del requirements
        return ()


_EVERYTHING_AVAILABLE = _NothingNarrows()


@dataclass(frozen=True, slots=True)
class _Selection:
    """What one investigation was offered, or why it was offered nothing.

    Both in one value because they are one decision: a run whose narrowed
    catalogue is empty must not reach the model at all, and returning an empty
    tuple would leave that decision to be made again by the caller.
    """

    tools: tuple[RegisteredTool, ...]
    outcome: InvestigationOutcome | None


def _uncarried(found: RegisteredTool) -> ExcludedCapability:
    """Return why a write this deployment cannot carry out was left out.

    Recorded rather than dropped. A capability missing from a run's catalogue
    looks identical whether it was never written or is simply not something
    this deployment can perform, and only one of those is something an operator
    can change.
    """
    return ExcludedCapability(
        name=found.name,
        kind=CapabilityKind.TOOL,
        unmet=("a composed remediation desk with components for this capability",),
    )


def _outcome_summary(outcome: InvestigationOutcome) -> str:
    """Return the run's answer when it ended before the model was called."""
    parts = [outcome.headline, outcome.detail, *outcome.next_steps]
    return " ".join(part for part in parts if part)


def _degraded_summary(answer: str) -> str:
    """Return a degraded run's summary, naming the degradation by its canonical word.

    ``answer`` already carries the operator-facing detail: what the run
    gathered, and why it stopped short of a full answer. This only makes sure
    the product's own word for the state — "degraded" — is actually present,
    rather than left for a reader to infer from a sentence that never uses
    it, or lost entirely once nothing downstream reads ``RunResult.degraded``
    itself.
    """
    detail = answer or "no evidence was gathered before the run ended"
    return f"degraded: {detail}"


__all__ = [
    "ENVIRONMENT_KEY",
    "InvestigationDidNotComplete",
    "NoPendingInteraction",
    "ReActInvestigationRunner",
    "team_availability",
]
