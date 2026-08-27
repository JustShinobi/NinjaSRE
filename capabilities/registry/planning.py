"""The tier-2 half of the pipeline's catalogue and ranking ports.

The investigation pipeline is tier 3 and this package is tier 2, so the
pipeline cannot import the scorer or the resolver — it declares what it needs
and something above both substitutes an implementation. This module is that
implementation. Two of the three things here are deliberately thin adapters
with no behaviour of their own, so the ranking a run got is the ranking
``scoring.rank`` produces and nothing about the pipeline changed it on the way
through.

The composition root wires them::

    resolver = TeamCatalogueResolver(build_registry())
    ranker = CatalogueRanker()

The serving path builds both — the resolver through ``for_availability``,
because it holds a request rather than a pipeline state.

``TurnCatalogueSelector`` is the third, and it is not an adapter. It answers
"what does *this turn* carry", which is a question with a different answer on
every turn of a run: the ranking is re-run against what the investigation has
learned by then, under the same unchanged cap. It lives here rather than in the
loop for the same tier reason as the other two — the loop is handed a callable
and cannot reach for the scorer itself.

Substituting any of them is how an ablation is run. Putting the substitution
here rather than inside a stage is what makes "the plan contributed this much"
a measurement rather than an argument, and the same seam makes "re-ranking
contributed this much" measurable: hand the loop no selector and every run
behaves exactly as it did when selection ran once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from capabilities.registry.catalogue import Registry, ResolvedCatalogue, resolve_for
from capabilities.registry.disclosure import DiscoveredSkill
from capabilities.registry.scoring import Incident, ScoredCapability, rank, terms
from capabilities.registry.selection import select
from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MAX_SECONDARY_FALLBACK_TOOLS,
    MAX_TURN_RANKING_CHARS,
    MAX_TURN_RANKING_EVIDENCE,
)
from core.capability.metadata import CapabilityKind, CapabilityMetadata, ToolMetadata
from core.capability.ports import (
    ConfiguredIntegrations,
    EffectivenessProvider,
    IntegrationAvailability,
    NeutralEffectiveness,
)
from core.capability.registered import RegisteredTool
from core.pipeline.ports import IncidentSignals, RankedCapability
from core.state.agent_state import AgentState


@dataclass(frozen=True, slots=True)
class CatalogueRanker:
    """Scores a catalogue with the deterministic scorer this package owns.

    ``effectiveness`` is the memory layer's contribution and defaults to the
    neutral provider, which removes the term entirely. That default is also the
    ablation control: a learning mechanism whose contribution cannot be
    switched off cannot be measured.
    """

    effectiveness: EffectivenessProvider = field(default_factory=NeutralEffectiveness)

    def rank(
        self, declarations: Sequence[CapabilityMetadata], signals: IncidentSignals
    ) -> Sequence[RankedCapability]:
        """Return every declaration scored against ``signals``, highest first."""
        scored = rank(
            declarations,
            Incident(
                alert_source=signals.alert_source,
                summary=signals.summary,
                tags=signals.tags,
                domain=signals.domain,
                planned_capabilities=signals.planned_capabilities,
                subject_sources=signals.subject_sources,
            ),
            effectiveness=self.effectiveness,
        )
        return tuple(
            RankedCapability(name=entry.name, score=entry.score, rationale=entry.rationale)
            for entry in scored
        )


@dataclass(frozen=True, slots=True)
class TurnProgress:
    """What a run has learned by the time its next turn is ranked.

    Deliberately two fields, and they answer different questions.

    ``learned`` is the incident as the run now understands it, most recent
    first: what the last calls returned, and what the model said it was looking
    for. It is what stops re-ranking from being the same ranking computed twice
    — an investigation that has established the failure is a Proxmox backup job
    ranks nothing like the Alertmanager notification it started from.

    ``in_flight`` is the capabilities the model is mid-way through using. They
    are pinned rather than scored, because the alternative is a tool that
    vanishes underneath a call in progress: the model asks a follow-up of
    something it was holding one turn ago and is told the capability is
    unknown. That reads as a model defect and is a selection one.

    Stated as plain text and plain names rather than as a session, so this
    package does not have to know what a run looks like. Extracting them is the
    runtime's job; scoring against them is this one's.
    """

    learned: tuple[str, ...] = ()
    in_flight: tuple[str, ...] = ()


#: A turn with nothing behind it: the opening one. Ranks on the alert alone,
#: which is exactly what selection did before it ran per turn.
NO_PROGRESS: TurnProgress = TurnProgress()


@dataclass(frozen=True, slots=True)
class TurnSelection:
    """What one turn carries, and the ranking that decided it.

    ``ranked`` covers every declaration the turn chose between, tools and
    skills together; ``cut`` is the tools among them the ceiling took. Both are
    here because only together do they answer the question an operator arrives
    with: "these were offered" cannot distinguish a capability that scored badly
    from one that scored well and lost to the ceiling, and those have opposite
    fixes.
    """

    tools: tuple[RegisteredTool, ...] = ()
    skills: tuple[DiscoveredSkill, ...] = ()
    ranked: tuple[RankedCapability, ...] = ()
    cut: tuple[RankedCapability, ...] = ()


def _ranked(entry: ScoredCapability) -> RankedCapability:
    """Return the scorer's own verdict in the shape the pipeline reads."""
    return RankedCapability(name=entry.name, score=entry.score, rationale=entry.rationale)


@dataclass(frozen=True, slots=True)
class TurnCatalogueSelector:
    """Chooses the bounded set again before every turn, from what the run knows.

    Selection used to run once, before the first model call, and the toolset was
    then fixed for the whole investigation. A staging run recorded its own
    verdict on that::

        ranked 76, offered 40, cut by the ceiling 20

    Twenty capabilities that were not missing from a turn — they were
    unreachable for the run, with nothing the model observed or said able to
    bring one back.

    The cap is not what was wrong and does not move. It bounds a turn's payload,
    which is a claim about what is sent to a model rather than about what a run
    may ever reach; the implementation had quietly turned the first into the
    second. So the ceiling is re-applied to every turn and *which* capabilities
    fill it is re-decided every turn, and over a run the whole catalogue is
    reachable while no single turn ever carries more than the bound.

    The cut is delegated to ``selection.select`` rather than taken as a top-N
    here, which is what keeps the four things that selection does and a top-N
    does not — plan entries first, the tools a chosen methodology directs, the
    reserve for cheap reasoning, and anti-example suppression — true of every
    turn rather than only of the first.
    """

    catalogue: ResolvedCatalogue
    opening: Incident
    effectiveness: EffectivenessProvider = field(default_factory=NeutralEffectiveness)
    max_schemas: int = MAX_AGENT_TOOL_SCHEMAS
    reserved: int = MAX_SECONDARY_FALLBACK_TOOLS

    def signals(self, progress: TurnProgress = NO_PROGRESS) -> Incident:
        """Return the opening incident widened by what the run has since learned.

        The opening summary is kept whole and the run's progress is appended to
        it rather than replacing it. An investigation does not stop being about
        the alert that started it, and a ranking that read only the last few
        observations would chase whatever the previous turn happened to touch.

        The load-bearing part is not the summary, though. Lexical overlap is the
        weakest term in the formula, and a run that has *established* which
        vendor holds the broken thing has learned the strongest one: the subject
        source, worth four times what the alert source is worth, and worth it
        precisely because a backup job failing on a Proxmox node is a question
        about Proxmox however it was delivered. Before the first turn that fact
        comes from alert resolution. After it, it comes from the investigation —
        so a declared evidence source or tag that turns up in what the run has
        observed is read as the incident naming it.

        Read against the catalogue's own declared vocabulary rather than against
        a list of vendor names written here. Nothing is invented: a word only
        counts because some capability declared it about itself and the run then
        observed it.

        ``in_flight`` enters as plan entries, ahead of anything the opening plan
        named. That is not a new mechanism: selection already offers everything
        the plan named first, so pinning is expressed in the vocabulary the
        selection already has rather than as a second rule that could disagree
        with it.
        """
        learned = _bounded(progress.learned)
        observed = terms(learned)
        pinned = tuple(dict.fromkeys((*progress.in_flight, *self.opening.planned_capabilities)))
        declared_sources, declared_tags = self._vocabulary()
        return Incident(
            alert_source=self.opening.alert_source,
            summary=" ".join(part for part in (self.opening.summary, learned) if part),
            tags=tuple(dict.fromkeys((*self.opening.tags, *sorted(declared_tags & observed)))),
            domain=self.opening.domain,
            planned_capabilities=pinned,
            subject_sources=tuple(
                dict.fromkeys((*self.opening.subject_sources, *sorted(declared_sources & observed)))
            ),
        )

    def _vocabulary(self) -> tuple[frozenset[str], frozenset[str]]:
        """Return the evidence sources and tags this catalogue declares about itself."""
        sources: set[str] = set()
        tags: set[str] = set()
        for declaration in self.catalogue.metadata():
            tags.update(tag.strip().lower() for tag in declaration.tags if tag.strip())
            # Only a tool names a system its evidence comes from. A methodology
            # has none, which is why it contributes tags here and nothing else.
            if isinstance(declaration, ToolMetadata):
                source = declaration.evidence_source.strip().lower()
                if source:
                    sources.add(source)
        return frozenset(sources), frozenset(tags)

    def for_turn(self, progress: TurnProgress = NO_PROGRESS) -> TurnSelection:
        """Return what this turn carries, under the cap, with the ranking behind it."""
        result = select(
            self.catalogue,
            self.signals(progress),
            effectiveness=self.effectiveness,
            max_schemas=self.max_schemas,
            # A deployment that lowers the ceiling below the reserve wants a
            # smaller turn, not the refusal ``select`` would otherwise raise.
            reserved=min(self.reserved, max(self.max_schemas - 1, 0)),
        )
        offered = {found.name for found in result.tools}
        return TurnSelection(
            tools=tuple(result.tools),
            skills=tuple(result.skills),
            ranked=tuple(_ranked(entry) for entry in result.scores),
            cut=tuple(
                _ranked(entry)
                for entry in result.scores
                if entry.kind is CapabilityKind.TOOL and entry.name not in offered
            ),
        )


def _bounded(learned: Sequence[str]) -> str:
    """Return the run's progress as one string, inside both of its budgets.

    Two bounds rather than one because they fail differently. The entry count
    keeps a long run from carrying its whole history into every ranking; the
    character bound keeps a single observation from doing the same on its own,
    which one megabyte of log lines otherwise would. The second is the one that
    silently matters: the scorer's lexical term is a ratio over the union of
    both vocabularies, so an unbounded incident side drives every use-case
    overlap towards zero and turns the term off without failing anything.
    """
    kept = [part.strip() for part in learned[:MAX_TURN_RANKING_EVIDENCE] if part.strip()]
    return " ".join(kept)[:MAX_TURN_RANKING_CHARS]


@dataclass(frozen=True, slots=True)
class TeamCatalogueResolver:
    """Resolves the built registry against the integrations a run's team has.

    Availability comes from the team on the state rather than from a captured
    value, so one resolver serves every team in a multi-tenant deployment —
    which is the shape a shared registry and per-team configuration imply.
    """

    registry: Registry

    async def resolve(self, state: AgentState) -> ResolvedCatalogue:
        """Return what the team on ``state`` can run, with the exclusions."""
        return self.for_availability(self.availability(state))

    def for_availability(self, availability: IntegrationAvailability) -> ResolvedCatalogue:
        """Return what a team with ``availability`` can run, with the exclusions.

        The entry for a caller that has the availability already and holds no
        pipeline state — the path that serves a request holds a request. It is
        the same resolution ``resolve`` performs, called from one place rather
        than written twice: two implementations would be two answers to "what
        can this team run", and the day they drifted a screen would count one
        number while an investigation was handed another.
        """
        return resolve_for(self.registry, availability)

    def availability(self, state: AgentState) -> IntegrationAvailability:
        """Return what this run's team has configured."""
        return ConfiguredIntegrations(
            integrations=state.team.integrations,
            sandbox_profiles=state.team.sandbox_profiles,
        )


__all__ = [
    "NO_PROGRESS",
    "CatalogueRanker",
    "TeamCatalogueResolver",
    "TurnCatalogueSelector",
    "TurnProgress",
    "TurnSelection",
]
