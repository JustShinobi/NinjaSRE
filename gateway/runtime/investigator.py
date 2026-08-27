"""Running the six stages from the eight-method contract the routes hold.

``ReActInvestigationRunner`` is the first implementation of
``gateway.http.services.InvestigationRunner`` this repository ships — every
deployment before this feature ran ``UnconfiguredInvestigator``, whichever
factory it named. What it drives is ``core.pipeline.build.build_pipeline``: the
six stages `/agent` has always told an operator an investigation runs, built
fresh per investigation and run in order.

The canonical loop is still here and still the thing that investigates. It is
what the gathering stage is constructed with — one stage of six rather than a
second orchestration beside them — and it is composed here rather than inside
the stage because the model's tool-schema ceiling is smaller than the declared
capability catalogue, and which tools are worth offering depends on what the
alert is about and on what this deployment can carry out. Narrowing has to
happen before the loop is constructed, not after, since the loop's own
constructor refuses to be built beyond that ceiling.

Four things are built per investigation and never per process, and the reason
is the same for all four: they carry the identity of one run.

**The remediation gate**, when this deployment composed a desk. Its run context
names who asked and for which team, so a gate shared between runs would propose
changes attributed to whoever happened to build it.

**The question desk**, so a person answering on one incident cannot close the
question another incident raised. That is the failure a process-wide binding
produces and the one nobody would notice.

**The read sources** recall and topology answer from, when this deployment
supplied factories to build them with. Each is scoped to one team, and the
capability that reads it has no constructor to be handed one — it reads a
binding. Bound around the run rather than at boot, and put back afterwards
however the run ended: three investigations started inside 82 milliseconds here,
and a source left over from one of them is the next one searching another team's
incidents.

Episodic memory arrives through that same seam and carries one thing more. What
a deployment composes for a run is a search *and* the hook that records the run
at its end, because the corpus the search reads is built from nothing else — an
investigation that finishes without leaving an episode behind is one more empty
answer for every investigation after it.

**The tool selection**, narrowed three ways — by the integrations the team has
connected, by whether this deployment could carry a write out at all, and by
whether a read has anything bound to read from — and only then handed to
``capabilities.registry.selection.select``, which does the ranking, the
plan-first ordering, the skill-directed pull, the reserve and the cut.
Narrowing first matters: cutting before it spends slots of a small budget on
capabilities that were about to be removed.

That cut is made again before every turn, not once before the first. The
ceiling is a bound on what one turn sends, and holding a single selection for
the whole run had turned it into a bound on what the run could ever reach — a
staging investigation ranked 76 capabilities, was offered 40, and spent twenty
iterations unable to call any of the rest whatever it went on to establish. So
this runner hands the loop a selector rather than only a tuple, and the loop
asks it again each turn, against what the run has learned by then. The cap is
unchanged and applies to every one of those payloads; what moves is which
capabilities fill it.

Steering a running investigation — cancelling it, taking it over, queuing a
message, resuming it — is served against the same loop instance, tracked in
memory for the run's identity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field, replace
from typing import Any

from capabilities.registry.catalogue import Registry, ResolvedCatalogue
from capabilities.registry.disclosure import DiscoveredSkill
from capabilities.registry.planning import (
    CatalogueRanker,
    TeamCatalogueResolver,
    TurnCatalogueSelector,
    TurnProgress,
    TurnSelection,
)
from capabilities.registry.scoring import Incident
from capabilities.tools.system.memory_search import binding as recall_binding
from capabilities.tools.system.memory_search.binding import RecallSource
from capabilities.tools.system.sources import has_a_source, unmet_source
from capabilities.tools.system.topology_query import binding as topology_binding
from capabilities.tools.system.topology_query.binding import TopologySource
from config.constants.estate import (
    ALERT_DOMAIN_LABEL,
    ALERT_RANKING_TAG_LABELS,
    SUBJECT_CONTEXT_RESOURCE_KIND,
    SUBJECT_CONTEXT_RESOURCE_NAME,
    SUBJECT_CONTEXT_RESOURCE_SOURCE,
)
from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MAX_SECONDARY_FALLBACK_TOOLS,
)
from config.prompts import INVESTIGATION_SYSTEM_PROMPT
from core.agent.handoff import HANDOFF_CAPABILITY, HumanHandoff
from core.agent.hooks.registry import HookRegistry
from core.agent.interaction.models import Interaction
from core.agent.interaction.registry import InteractionRegistry
from core.agent.message_queue import MessageQueue
from core.agent.react_loop import ReActLoop, TurnToolSelector
from core.agent.runtime_port import RunStatus
from core.agent.session import Session
from core.capability.metadata import CapabilityKind, ExcludedCapability
from core.capability.ports import ConfiguredIntegrations, IntegrationAvailability
from core.capability.registered import RegisteredTool
from core.domain.alerts.normalisation import RawAlert
from core.llm.types import LLMClient
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import Pipeline, PipelineRun
from core.pipeline.ports import (
    NO_CATALOGUE,
    FixedCatalogueResolver,
    StaticCatalogue,
)
from core.pipeline.stages.resolve_integrations import zero_integration_outcome
from core.pipeline.state_factory import initial_state
from core.pipeline.streaming import EventStream
from core.state.agent_state import AgentState
from core.state.catalogue import ResolvedCapabilities
from core.state.types import InvestigationOutcome, TeamContext
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


#: How a deployment builds one investigation's recall path. Handed the request
#: because the source is scoped to a team and the team is named on it, and
#: awaited because building one can mean resolving that team's memory policy
#: first.
RecallSourceFactory = Callable[[InvestigationStart], Awaitable[RecallSource | None]]

#: The same, for the graph a topology question traverses.
TopologySourceFactory = Callable[[InvestigationStart], Awaitable[TopologySource | None]]


@dataclass(frozen=True, slots=True)
class RunMemory:
    """One investigation's episodic memory, as this deployment composed it.

    Two halves, and they arrive together because they are two ends of one
    mechanism: ``recall`` searches the corpus and ``hooks`` installs what writes
    into it at run end. Composing only the first is worse than composing
    neither — a bound search over a corpus nothing fills answers "no similar
    incidents" forever, and that is the sentence the capability exists to keep
    an investigation from saying on the strength of a store nobody configured.

    They come from one composition rather than two for a second reason as well.
    The recall ledger the retriever fills during the run is the one the episode
    reads at the end to record which recalls the answer actually used, and two
    compositions would be two ledgers and a corpus that can never say whether
    consulting it was worth anything.

    Either half may be absent, because a team switches reading and writing
    separately: ``recall`` is ``None`` for a team that may write but not read —
    the ablation of a populated corpus nobody consults — and the capability is
    then withheld rather than offered with nothing behind it.
    """

    recall: RecallSource | None = None
    hooks: Callable[[HookRegistry], object] | None = None


#: How a deployment builds one investigation's memory. Handed the request for the
#: reason a recall factory is, and awaited because building it means resolving
#: that team's memory policy first.
RunMemoryFactory = Callable[[InvestigationStart], Awaitable[RunMemory | None]]


@dataclass(frozen=True, slots=True)
class _SourceComposition:
    """The factories this deployment supplied for the reads that need a source.

    Any of them may be absent, and absent means *leave that binding untouched*
    rather than bind nothing. A deployment that binds a source at boot, and a
    test that binds one around a call, both keep behaving exactly as they did —
    the seam adds a way to scope a source to a run and takes nothing away.

    ``recall`` and ``memory`` compose the same binding and never both: the first
    is for a deployment that has somewhere to search and nowhere to record, and
    the second carries the write half with it.
    """

    recall: RecallSourceFactory | None = None
    topology: TopologySourceFactory | None = None
    memory: RunMemoryFactory | None = None


@contextmanager
def _bound[Source](
    bind: Callable[[Source | None], Source | None],
    restore: Callable[[Source | None], None],
    source: Source | None,
) -> Iterator[Source | None]:
    """Bind ``source`` for the body and put back whatever it displaced.

    The ``finally`` is the point: a run that raised is the one whose leftover
    binding does the damage, because the next investigation in this process
    would search with it.
    """
    previous = bind(source)
    try:
        yield source
    finally:
        restore(previous)


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
    _sources: _SourceComposition = field(default_factory=_SourceComposition, repr=False)

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

    def attach_sources(
        self,
        *,
        recall: RecallSourceFactory | None = None,
        topology: TopologySourceFactory | None = None,
        memory: RunMemoryFactory | None = None,
    ) -> None:
        """Give this runner what to build each investigation's read sources with.

        Merged rather than replaced, so recall, topology and memory can be
        composed by whoever owns each without the second call dropping the
        first: a factory named here takes the place of the one held for that
        source, and one left out leaves that source as it was. Passing none is
        a no-op.

        ``memory`` composes the recall binding *and* the episode write, and is
        therefore refused alongside ``recall``, which composes the binding
        alone. Two composers for one binding is a wiring mistake, and a silent
        precedence between them is one nobody would ever find from a run's
        behaviour.

        A runner nobody called this on binds nothing and behaves exactly as it
        did — a deployment that binds its sources at boot keeps working, and a
        capability whose source is bound that way is still offered.

        Scoped to ``investigate`` and to nothing else. A run handed back by
        ``resume`` is driven outside that scope and reads whatever its own
        context holds, which is the same gap resume already has for the trace it
        does not write.
        """
        merged = replace(
            self._sources,
            recall=recall if recall is not None else self._sources.recall,
            topology=topology if topology is not None else self._sources.topology,
            memory=memory if memory is not None else self._sources.memory,
        )
        if merged.recall is not None and merged.memory is not None:
            raise ValueError(
                "this runner was given both a recall factory and a memory factory, and "
                "they compose the same binding. Compose memory, which carries the "
                "episode write with it, or compose recall alone — never both."
            )
        self._sources = merged

    @property
    def can_record(self) -> bool:
        """Return whether this runner has somewhere to write what it does."""
        return self._recording is not None

    @property
    def remediation(self) -> Any:
        """Return the composed remediation desk, or ``None`` when there is none."""
        return self._remediation

    @property
    def sources(self) -> _SourceComposition:
        """Return the factories this deployment attached, for a composition to assert on.

        What a composition root built is the only evidence that a source reaches
        a run at all: a factory nothing attached is the state this deployment
        was in for every investigation it has ever run.
        """
        return self._sources

    async def investigate(self, request: InvestigationStart) -> str:
        """Run the six stages to completion and return the investigation's summary.

        The stages are what runs, not a loop standing in for them. `/agent` has
        always told an operator that an investigation resolves integrations,
        takes the alert in, plans its evidence, gathers it, diagnoses, and
        delivers — and until this composed the pipeline, a served run did the
        fourth of those and nothing else. The loop is still the thing that
        investigates; it is what the gathering stage is built with, which is
        one stage of six rather than the whole of the run.

        Everything that is per-run is still built here and handed in, because
        all of it carries this run's identity: the loop, its hooks (the
        recorder, the remediation gate, the memory episode), the question desk,
        the message queue, and the catalogue narrowed for this team. The
        pipeline is built around them rather than reaching for any of them.

        Raises :class:`InvestigationDidNotComplete` when the gathering stage's
        runtime reported ``FAILED`` — it ran and produced nothing usable — so
        the caller records the run as failed rather than completed. A
        ``PARTIAL`` outcome is not this: it is a real completion on less
        evidence than the loop asked for, and is reported here with the
        product's own canonical word for that state — "degraded" — rather
        than as a summary a reader would have to infer the state from.

        A run whose team can execute nothing at all ends before the model is
        called, with the answer that names what to connect. Kept here rather
        than left to the resolving stage, which reaches the same answer a
        second way: reaching it there would cost intake's classification call
        first, and spending the run's only model call on its cheapest sentence
        is spending it on nothing.

        This run's read sources are bound before the catalogue is narrowed and
        stay bound until it ends, because the narrowing asks whether each one is
        bound and would otherwise exclude a capability this run can serve.
        """
        async with self._sources_bound_for(request) as memory:
            queue = MessageQueue(run_id=request.run_id)
            handoff = self._handoff_for(request)
            selection = await self._select_tools(request, handoff=handoff)

            if selection.outcome is not None:
                return _outcome_summary(selection.outcome)

            # One recorder, handed to both halves of the run. The loop gets it
            # as a turn hook and the pipeline gets it as a sink on its stream,
            # and it is the same object because that is the only thing joining
            # the two channels: the stage boundaries arrive on the stream, the
            # turns arrive from the loop, and a turn only knows which stage it
            # ran inside because one object saw both.
            recorder = self._recording_hook_for(request)
            loop = self._build_runtime(
                request,
                messages=queue,
                tools=selection.tools,
                rationale=selection.rationale,
                memory=memory,
                selector=selection.selector,
                recorder=recorder,
            )
            live = _LiveRun(loop=loop, messages=queue, handoff=handoff)
            self._live[request.run_id] = live

            run = await self._pipeline_for(
                request, runtime=loop, selection=selection, recorder=recorder
            ).run(_state_of(request, selection))

        return _summary_of(run)

    def _pipeline_for(
        self,
        request: InvestigationStart,
        *,
        runtime: ReActLoop,
        selection: _Selection,
        recorder: RunTraceRecordingHook | None = None,
    ) -> Pipeline:
        """Return the six stages, over what this run has already been given.

        The resolver is fixed to the catalogue ``_select_tools`` produced. It is
        not a shortcut: that narrowing asked what the team has connected, what
        this deployment could carry out, and what has a source to read, and the
        runtime handed in here is holding its answer. Resolving a second time
        inside the stage would be a second answer to the same question, and the
        day the two disagree the model is offered a tool the loop cannot call.

        The ranker is the capability package's own deterministic scorer — the
        same one the selection above ranked with, so the plan the stage writes
        and the tools on offer come from one formula rather than two.

        Recent incidents are the neutral index and delivery destinations are
        empty, and both are honest rather than unfinished. Deduplication
        already happened before this runner was reached: a webhook joins a
        burst onto an open incident and ``start_investigation`` attaches the
        run to it, in the transaction that reserves the run's identity. A
        second index here would be a second answer to a question with one
        writer. Nothing in this repository implements a delivery destination
        yet, so the stage records that the report was produced and not shipped
        — which is true, and is where it is: in the run's own record.

        ``recorder`` is on the stream rather than in the stage list, and it is
        the one thing here that is not per-stage configuration. The pipeline
        announces every stage boundary on that stream; a recorder listening to
        it can say which stage each of the loop's turns belonged to, and can
        write down what the four stages that never turn established. Without
        it the trace is a flat list of loop iterations, which is a complete
        account of one stage of six.
        """
        return build_pipeline(
            llm=self.llm,
            runtime=runtime,
            resolver=FixedCatalogueResolver(selection.catalogue),
            ranker=CatalogueRanker(),
            stream=EventStream(request.run_id, (recorder,)) if recorder is not None else None,
            system_prompt=self._system_prompt_for(selection),
            context=dict(request.context),
        )

    def _system_prompt_for(self, selection: _Selection) -> str:
        """Return what the investigating half of this run runs under.

        Named rather than left empty. Empty means the loop's own fallback,
        which is written for a sub-agent or a one-off question and frames the
        job as investigating and nothing else — with no mention that a
        remediation capability in the toolset becomes a proposal rather than an
        effect. An incident investigation is the one caller whose toolset can
        hold such a capability, so it is the one caller that has to say so.

        The methodologies selection chose are appended to it, bodies and all.
        This is the payout of progressive disclosure and the reason the skill
        index is worth its per-turn cost: a body is read from disk and put in
        front of the model only on the investigation that selected it. A
        deployment that selected a skill and never showed it would be paying
        the index every turn and collecting nothing.
        """
        return _prompt_with(INVESTIGATION_SYSTEM_PROMPT, selection.skills)

    @asynccontextmanager
    async def _sources_bound_for(
        self, request: InvestigationStart
    ) -> AsyncIterator[RunMemory | None]:
        """Bind this run's read sources for the body, and put back what they displaced.

        One scope rather than a binding per capability body, because the
        narrowing that decides whether a capability is offered at all reads the
        same bindings the capability does — they have to be set before the
        catalogue is built and still set when the model calls the tool.

        A source this deployment supplied no factory for is left exactly as it
        is, unbound or bound at boot. Building nothing is different from binding
        nothing, and only the second is a behaviour change for a caller that
        asked for none.

        What is yielded is this run's memory, because its other half — the hook
        that writes the episode — belongs to the runtime built inside this
        scope. Returning it rather than stashing it is what keeps one run's
        composition from reaching another's loop.
        """
        composed = self._sources
        with ExitStack() as scope:
            memory: RunMemory | None = None
            if composed.memory is not None:
                memory = await composed.memory(request)
                scope.enter_context(
                    _bound(
                        recall_binding.bind,
                        recall_binding.restore,
                        memory.recall if memory is not None else None,
                    )
                )
            elif composed.recall is not None:
                scope.enter_context(
                    _bound(
                        recall_binding.bind,
                        recall_binding.restore,
                        await composed.recall(request),
                    )
                )
            if composed.topology is not None:
                scope.enter_context(
                    _bound(
                        topology_binding.bind,
                        topology_binding.restore,
                        await composed.topology(request),
                    )
                )
            yield memory

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

    async def queue_message(self, run_id: str, text: str) -> bool:
        """Queue ``text`` for delivery on the run's next turn, and say whether it landed.

        ``False`` when ``run_id`` names nothing this process is driving — there
        is no turn boundary left to deliver it at. Reported rather than
        swallowed: a caller that attached an incident to this run because it
        was about to tell it something has to be able to undo that decision.
        """
        live = self._live.get(run_id)
        if live is None:
            return False
        live.messages.submit(text, author="operator")
        return True

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
        rationale: str = "",
        memory: RunMemory | None = None,
        selector: TurnCatalogueSelector | None = None,
        recorder: RunTraceRecordingHook | None = None,
    ) -> ReActLoop:
        """Return the canonical loop, carrying at most the tools the model may hold.

        ``tools`` and ``rationale`` are the opening turn's, and ``selector`` is
        what replaces both before every turn after it. Handing over all three
        rather than only the selector keeps the loop's own cap check on a real
        payload at construction: a run that could never send a legal first turn
        should fail where it is composed, not on its third iteration.

        ``recorder`` is passed in rather than built here because the pipeline
        needs the same instance — it is the object that sees both the loop's
        turns and the pipeline's stage boundaries, and two of them would see
        one channel each and correlate nothing. A caller with none gets one
        built here, which is what keeps this method usable on its own.
        """
        hooks = investigation_hooks(
            recorder=recorder if recorder is not None else self._recording_hook_for(request)
        )
        if self._remediation is not None:
            # Registered at ``pre_tool_use`` after the guardrails and before
            # anything else, carrying this run's own context. It is the point
            # that decides whether a tool call may happen at all, which is why
            # a write cannot reach a capability body by any other route.
            self._remediation.gate_for(self._run_context(request)).register(hooks)
        if memory is not None and memory.hooks is not None:
            # The half of memory that is not a binding. Which hooks it installs
            # is the team's policy to decide — a team that may write gets the
            # episode at run end, a team that may read gets the paragraph
            # telling the agent memory exists — and a switched-off mechanism
            # registers nothing rather than registering a hook that returns
            # early, so "memory off" is the same dispatch order a deployment
            # without memory has.
            memory.hooks(hooks)
        return ReActLoop(
            llm=self.llm,
            tools=tools,
            hooks=hooks,
            messages=messages,
            selection_rationale=rationale,
            turn_tools=_reranks_every_turn(selector) if selector is not None else None,
        )

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

        The first three narrowings are facts about the deployment and hold for
        the whole run, so they are answered once. The fourth is a fact about
        the incident, which the run is in the business of changing its mind
        about — so the ranking is returned as a selector the loop asks again
        before every turn, and the tuple returned beside it is only the opening
        turn's answer.
        """
        availability = await self._availability(request)
        catalogue = TeamCatalogueResolver(self.registry).for_availability(availability)
        connected = tuple(getattr(availability, "integrations", ()) or ())
        carriable = tuple(
            found for found in catalogue.tools if self._can_carry(found) and self._can_answer(found)
        )
        excluded = (
            catalogue.excluded
            + tuple(_uncarried(found) for found in catalogue.tools if not self._can_carry(found))
            + tuple(
                _unsourced(found)
                for found in catalogue.tools
                if self._can_carry(found) and not self._can_answer(found)
            )
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

        # Fourth, hand the bounded catalogue to the selection the capability
        # package owns, rather than taking the top N of a ranking here.
        #
        # This runner used to do the cut itself, and the four things
        # ``select`` does that a top-N does not were therefore written,
        # tested, and unreachable from a serving deployment: plan entries
        # first, the tools a selected skill directs, the reserve that keeps
        # cheap reasoning and recall capabilities from being crowded out by a
        # well-integrated vendor, and the anti-example suppression that drops
        # a capability whose own author said "not for this".
        #
        # The skills ``select`` chooses are returned with the tools, and both
        # halves of a skill are then spent: the tools it directs are offered,
        # and its body is loaded into this turn's system prompt
        # (``_request_of``). A methodology selected and never shown would be a
        # catalogue index paid for on every turn and collected on none.
        narrowed = ResolvedCatalogue(
            tools=tuple(offered.values()),
            skills=tuple(catalogue.skills),
            excluded=tuple(excluded),
        )
        # The ceiling is this runner's to state — it is a property of the
        # model the deployment runs, not of the capability package.
        #
        # Held as a selector rather than spent here, because the answer is not
        # one answer. This is the opening turn's; the loop asks the same object
        # again before every turn that follows, and gets the ranking as the run
        # understands the incident by then. That is what makes the capabilities
        # this cut leaves out reachable later rather than for ever gone.
        selector = TurnCatalogueSelector(
            catalogue=narrowed,
            opening=self._ranking_signals(request),
            max_schemas=MAX_AGENT_TOOL_SCHEMAS,
            reserved=MAX_SECONDARY_FALLBACK_TOOLS,
        )
        turn = selector.for_turn()
        chosen = tuple(turn.tools)
        return _Selection(
            tools=chosen,
            selector=selector,
            outcome=None,
            catalogue=StaticCatalogue(
                tools=chosen,
                excluded=tuple(excluded),
                # The offered tools' own declarations plus the skills that were
                # discovered, which is what the resolving stage means by "every
                # available declaration" and what the plan is then scored over.
                declarations=(
                    *(found.metadata for found in chosen),
                    *(skill.metadata for skill in catalogue.skills),
                ),
            ),
            integrations=connected,
            skills=tuple(turn.skills),
            rationale=_selection_rationale(turn),
        )

    def _ranking_signals(self, request: InvestigationStart) -> Incident:
        """Return what is known about the incident when capabilities are ranked.

        Four of these five fields were never filled by this runner, so four of
        the scorer's terms could not fire in a deployment however carefully
        they were weighted. Everything read here is already on the request:
        intake resolved the alert onto an estate resource and wrote what it
        found into the run's context, and the alert's own labels ride along
        beside it.

        The summary is widened past the objective on purpose. The objective a
        detector writes names its subject by opaque identifier
        (``res-76ab…``), and lexical overlap against an identifier matches
        nothing — so the resource's name and kind are appended, which is how
        "pve01" and "node" reach a term that is looking for them.
        """
        context = request.context
        labels = request.alert_labels
        subject_source = str(context.get(SUBJECT_CONTEXT_RESOURCE_SOURCE, "")).strip()
        subject_kind = str(context.get(SUBJECT_CONTEXT_RESOURCE_KIND, "")).strip()
        subject_name = str(context.get(SUBJECT_CONTEXT_RESOURCE_NAME, "")).strip()
        return Incident(
            alert_source=request.alert_source,
            summary=" ".join(
                part for part in (request.objective, subject_name, subject_kind) if part
            ),
            tags=_ranking_tags(labels, kind=subject_kind, source=subject_source),
            domain=str(labels.get(ALERT_DOMAIN_LABEL, "")).strip(),
            subject_sources=(subject_source,) if subject_source else (),
        )

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

    def _can_answer(self, found: RegisteredTool) -> bool:
        """Return whether ``found`` has something to read in this process.

        The read-side counterpart of ``_can_carry``. Recall needs an episode
        corpus and topology needs a graph; unbound, each spends a turn telling
        the investigation that a source nobody composed is not composed. Every
        run this deployment has made called both, and every one of those calls
        failed.

        The unavailability itself is right and stays: a tool asked without a
        source must say so rather than answer emptily, or an investigation
        concludes "no similar incidents" about a corpus that never existed.
        What changes is that it is not asked.
        """
        return has_a_source(found.name)


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
    #: The same narrowing, in the shape the resolving stage reads. Carried
    #: rather than rebuilt, so the catalogue the first stage writes into the
    #: run's state and the tools the runtime is holding are one answer: the
    #: excluded records travel with it, which is what lets a screen say why a
    #: capability was not on offer rather than leaving it silently absent.
    catalogue: StaticCatalogue = NO_CATALOGUE
    #: Which integrations this run's team has connected, as the configuration
    #: tree answered. Recorded on the run's own state, so a trace says what the
    #: team had rather than what the process happens to have registered.
    integrations: tuple[str, ...] = ()
    #: The methodologies selection chose for this incident. Their bodies are
    #: loaded into the turn that selected them and nowhere else, which is the
    #: whole of progressive disclosure: the index costs every turn, the body
    #: costs only the investigation that won it.
    skills: tuple[DiscoveredSkill, ...] = ()
    #: Why these were the ones on offer, in the scorer's own words, plus what
    #: the ceiling cut. Carried rather than logged: an operator asking why a
    #: capability was missing from a run is asking about that run, and a line
    #: in a process log has already scrolled past by the time they ask.
    rationale: str = ""
    #: The thing that produced ``tools``, kept so it can produce them again.
    #: The tuple above is one turn's answer; this is what answers the same
    #: question before each of the turns after it, against what the run has
    #: learned by then. Without it the opening cut would be permanent, which is
    #: what it was: a run ranked 76 capabilities, was offered 40, and could not
    #: reach the other 36 however the investigation went.
    selector: TurnCatalogueSelector | None = None


def _state_of(request: InvestigationStart, selection: _Selection) -> AgentState:
    """Return the state the six stages start this investigation from.

    Built through ``initial_state`` rather than by constructing an
    ``AgentState`` here, because that is the one function every surface starts
    from and a second construction path is how the webhook route and the corpus
    harness end up investigating subtly different things.

    Nothing is interpreted on the way in. The objective is carried as the raw
    text it is and the alert source as the hint the transport already knows,
    which is a fact, and intake is left to do the parsing — a state that
    arrived pre-normalised would have an alert before the stage that produces
    one, and the noise verdict would be about a value somebody else computed.
    """
    return initial_state(
        RawAlert(text=request.objective, source_hint=request.alert_source),
        TeamContext(
            team_id=request.team_node_id,
            integrations=selection.integrations,
            actor_id=request.principal_id,
        ),
        run_id=request.run_id,
    )


def _summary_of(run: PipelineRun) -> str:
    """Return the finished investigation's summary, or raise when it failed.

    The status is read from the accounting slice rather than from the run's
    outcome, because that is where the runtime's own verdict is written and
    nothing after gathering touches it. The outcome is read for the reason, and
    the delivery stage keeps a failed one rather than replacing it, which is
    what makes the reason still there to read.

    What comes back on a completed run is the agent's own answer, unchanged.
    ``gateway.http.orchestration._drive`` pulls the run's headline out of this
    string and stores the rest as the report body; returning the diagnosis
    stage's structured account instead would rewrite the shape of every report
    a deployment has, which is a separate decision from running the stages.
    """
    state = run.state
    outcome = state.investigation.outcome
    status = state.accounting.status

    if status == RunStatus.FAILED.value:
        detail = outcome.detail if outcome is not None else ""
        raise InvestigationDidNotComplete(detail or "the investigation produced no answer")
    if status == RunStatus.PARTIAL.value:
        return _degraded_summary(state.investigation.conclusion)
    if state.investigation.conclusion.strip():
        return state.investigation.conclusion
    if outcome is not None:
        # The run ended before the loop was ever driven — noise, a duplicate,
        # or a team with nothing to run. There is no agent answer to return and
        # the outcome is the whole of what happened.
        return _outcome_summary(outcome)
    return f"investigation ended {status or 'without a conclusion'}"


def _prompt_with(base: str, skills: Sequence[DiscoveredSkill]) -> str:
    """Return ``base`` with each selected methodology appended under its name.

    Named, because a body dropped into a prompt anonymously is prose the model
    cannot attribute or cite, and the investigation's own answer is supposed to
    be able to say which methodology it followed.
    """
    if not skills:
        return base
    sections = [f"## Methodology: {skill.name}\n\n{skill.body()}" for skill in skills]
    return "\n\n".join([base, *sections])


def _ranking_tags(labels: Mapping[str, str], *, kind: str, source: str) -> tuple[str, ...]:
    """Return the tags one incident is matched against a declaration by.

    The alert's own vocabulary plus what the estate says the subject is. A
    capability declares tags like ``backup`` or ``proxmox`` or ``node``, and
    until this existed nothing on the incident side was ever put beside them —
    the tag term of the formula could not fire in a deployment at all.
    """
    collected = {
        str(labels.get(label, "")).strip().lower()
        for label in ALERT_RANKING_TAG_LABELS
        if str(labels.get(label, "")).strip()
    }
    collected.update(part.lower() for part in (kind, source) if part)
    return tuple(sorted(collected))


def _selection_rationale(turn: TurnSelection) -> str:
    """Return why these capabilities were offered and what the ceiling cut.

    Both halves, because only together do they answer the question an operator
    actually arrives with. "These were offered" does not distinguish a
    capability that scored badly from one that scored well and lost to the
    ceiling, and those have opposite fixes: the first is a declaration whose
    use cases do not describe the incident, the second is a budget too small
    for a deployment this well connected.

    Written once per turn rather than once per run, and that is not a detail:
    once the offered set is re-decided every turn, an operator asking why a
    capability was missing is asking about a turn. A rationale carried forward
    from the opening selection would be describing a payload that no longer
    exists — and worse, it would say a capability was cut when the very next
    turn had gone and offered it.

    Scores are the scorer's own, not a re-derivation. A rationale computed a
    second way is a second opinion, and the day the two disagree the record
    stops being evidence.
    """
    by_name = {entry.name: entry for entry in turn.ranked}
    lines = [
        f"ranked {len(turn.ranked)}, offered {len(turn.tools)}, cut by the ceiling {len(turn.cut)}"
    ]
    for registered in turn.tools:
        entry = by_name.get(registered.name)
        if entry is None:
            continue
        why = "; ".join(entry.rationale) if entry.rationale else "no term matched"
        lines.append(f"+ {registered.name} ({entry.score:.3g}): {why}")
    if turn.cut:
        lines.append(
            "cut by the ceiling, highest first: "
            + ", ".join(f"{entry.name} ({entry.score:.3g})" for entry in turn.cut)
        )
    return "\n".join(lines)


def _turn_progress(session: Session) -> TurnProgress:
    """Return what this run has learned so far, in the shape the ranking reads.

    Most recent first, because both budgets on the ranker's input cut from the
    end: what the model just said about what it is looking for is the signal
    least worth losing to a long run's history.

    Two things go in and one deliberately stays out.

    In: the model's own words from the last turn, which is the "I need X" the
    fixed toolset had no way to hear at all; and the evidence summaries, newest
    first, which are what the run has actually established.

    Out: the *source* each evidence entry came from. Feeding that back would
    make selection self-reinforcing — a turn that called an Alertmanager tool
    would score Alertmanager tools higher on the next turn for no reason beyond
    having called one — and an investigation that entrenches its opening guess
    is the failure this whole mechanism exists to undo.

    ``in_flight`` is the previous turn's calls and only those. That is what
    "mid-way through using" means concretely: the model has a result in hand and
    a follow-up to make, and the capability has to still be there for it.
    """
    learned: list[str] = []
    if session.turns and session.turns[-1].rationale.strip():
        learned.append(session.turns[-1].rationale.strip())
    learned.extend(
        entry.summary.strip() for entry in reversed(session.evidence) if entry.summary.strip()
    )
    in_flight = tuple(
        dict.fromkeys(
            execution.capability
            for turn in session.turns[-1:]
            for execution in turn.executions
            if execution.capability
        )
    )
    return TurnProgress(learned=tuple(learned), in_flight=in_flight)


def _reranks_every_turn(selector: TurnCatalogueSelector) -> TurnToolSelector:
    """Return the callable the loop re-decides each turn's payload with.

    A closure over one run's own selector, so two investigations running side
    by side re-rank their own narrowed catalogues rather than a shared one.
    """

    def choose(session: Session) -> tuple[Sequence[RegisteredTool], str]:
        turn = selector.for_turn(_turn_progress(session))
        return tuple(turn.tools), _selection_rationale(turn)

    return choose


def _unsourced(found: RegisteredTool) -> ExcludedCapability:
    """Return why a read with nothing behind it was left out.

    Named as a requirement rather than as a fault, because it is one: the
    capability works and this deployment has not been given what it reads.
    An operator seeing "requires an episode corpus (memory)" knows what to do;
    one seeing the capability quietly absent does not.
    """
    return ExcludedCapability(
        name=found.name,
        kind=CapabilityKind.TOOL,
        unmet=(unmet_source(found.name),),
    )


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
    "RunMemory",
    "RunMemoryFactory",
    "team_availability",
]
