"""What the pipeline needs from layers it is not allowed to import.

The catalogue is resolved in `capabilities/`, ranking is scored there, recent
incidents come from persistence, and report destinations are transports. All
four are above or beside `core/` in the tier table, and the pipeline is tier 3.
So all four are ports here, each with a neutral default, and the composition
root substitutes the real one.

"Neutral" is a precise claim in every case, not a placeholder:

``NO_CATALOGUE``
    A team with nothing configured. The zero-integration path is what
    a run gets, which is the correct behaviour and a tested one.

``UNRANKED``
    Every capability scores zero, so the plan is empty and therefore advisory
    and therefore advisory. The loop falls back to its own relevance ranking, which is what
    it does anyway when the plan is weak.

``NO_RECENT_INCIDENTS``
    Nothing to deduplicate against, so every alert is investigated. That is the
    behaviour every alert had before deduplication existed.

``()`` destinations
    Nowhere to deliver. The diagnosis is still produced and still in the trace;
    only the shipping is absent.

Each of these is also the switch an ablation flips. A learning mechanism whose
contribution cannot be turned off cannot be measured, and turning it off means
substituting the neutral implementation rather than editing the stage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from core.capability.metadata import CapabilityMetadata, ExcludedCapability
from core.capability.registered import RegisteredTool
from core.domain.correlation.fingerprint import IncidentRef
from core.domain.diagnosis.result import Diagnosis
from core.state.agent_state import AgentState

# -- the capability catalogue -------------------------------------------------


@runtime_checkable
class Catalogue(Protocol):
    """What one team can run, as the capability layer resolved it.

    Structural, so the resolved catalogue the capability layer already builds
    satisfies it without importing anything from here — which is what keeps the
    dependency pointing downward.
    """

    @property
    def tools(self) -> Sequence[RegisteredTool]:
        """Return the tools this team can execute."""

    @property
    def excluded(self) -> Sequence[ExcludedCapability]:
        """Return what was left out, each with the requirement it is waiting on."""

    def metadata(self) -> Sequence[CapabilityMetadata]:
        """Return every available declaration, tools and skills together."""


@dataclass(frozen=True, slots=True)
class StaticCatalogue:
    """A catalogue stated outright. The neutral default and the test double."""

    tools: tuple[RegisteredTool, ...] = ()
    excluded: tuple[ExcludedCapability, ...] = ()
    declarations: tuple[CapabilityMetadata, ...] = ()

    def metadata(self) -> Sequence[CapabilityMetadata]:
        """Return every available declaration."""
        return self.declarations


#: A team with nothing configured.
NO_CATALOGUE: StaticCatalogue = StaticCatalogue()


@runtime_checkable
class CatalogueResolver(Protocol):
    """Answers what a given team has configured and credentialed."""

    async def resolve(self, state: AgentState) -> Catalogue:
        """Return the catalogue the team on ``state`` can run."""


@dataclass(frozen=True, slots=True)
class FixedCatalogueResolver:
    """Returns the same catalogue whoever asks. The neutral default."""

    catalogue: Catalogue = NO_CATALOGUE

    async def resolve(self, state: AgentState) -> Catalogue:
        """Return the catalogue this resolver was built with."""
        return self.catalogue


# -- ranking ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IncidentSignals:
    """What is known about the incident when capabilities are ranked.

    Deliberately small, and deliberately not the alert: everything here is
    available before the first model call of the gathering stage, because that
    is when ranking has to happen.
    """

    alert_source: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    domain: str = ""
    planned_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RankedCapability:
    """One capability's score against one incident, and how it got there."""

    name: str
    score: float = 0.0
    rationale: tuple[str, ...] = ()


@runtime_checkable
class CapabilityRanker(Protocol):
    """Scores a catalogue against one incident, deterministically."""

    def rank(
        self, declarations: Sequence[CapabilityMetadata], signals: IncidentSignals
    ) -> Sequence[RankedCapability]:
        """Return every declaration scored, highest first, ties broken by name."""


@dataclass(frozen=True, slots=True)
class UnrankedCapabilities:
    """Scores everything zero, which makes the resulting plan advisory.

    The ablation switch for planning: substitute this and the loop investigates
    on its own relevance ranking, which is the behaviour the plan is measured
    against.
    """

    def rank(
        self, declarations: Sequence[CapabilityMetadata], signals: IncidentSignals
    ) -> Sequence[RankedCapability]:
        """Return every declaration at zero, in name order."""
        return tuple(
            RankedCapability(name=entry.name, rationale=("no ranking configured",))
            for entry in sorted(declarations, key=lambda entry: entry.name)
        )


#: The ranker a pipeline built without one uses.
UNRANKED: UnrankedCapabilities = UnrankedCapabilities()


# -- recent incidents ---------------------------------------------------------


@runtime_checkable
class IncidentIndex(Protocol):
    """The incidents already open, as deduplication needs to see them."""

    async def recent(self, *, before: datetime) -> Sequence[IncidentRef]:
        """Return the incidents opened before ``before`` that are still current."""

    async def record(self, reference: IncidentRef) -> None:
        """Store ``reference`` so a later alert can be linked to it."""


@dataclass(slots=True)
class InMemoryIncidentIndex:
    """Incidents held for the life of the process.

    Enough for a single-process deployment and for the storm test, and
    deliberately not enough for a real one: persistence lands with the data
    platform, and this is what the pipeline uses until it does.
    """

    incidents: list[IncidentRef] = field(default_factory=list)

    async def recent(self, *, before: datetime) -> Sequence[IncidentRef]:
        """Return every held incident opened at or before ``before``."""
        return tuple(found for found in self.incidents if found.opened_at <= before)

    async def record(self, reference: IncidentRef) -> None:
        """Store ``reference``."""
        self.incidents.append(reference)


@dataclass(frozen=True, slots=True)
class NoIncidentIndex:
    """Knows of no incidents, so every alert is investigated."""

    async def recent(self, *, before: datetime) -> Sequence[IncidentRef]:
        """Return nothing."""
        return ()

    async def record(self, reference: IncidentRef) -> None:
        """Forget ``reference`` immediately."""


#: The index a pipeline built without one uses.
NO_RECENT_INCIDENTS: NoIncidentIndex = NoIncidentIndex()


# -- delivery -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeliveryPayload:
    """Everything a destination needs to render a report.

    The whole state rather than a pre-rendered string, because formatting is
    per destination: a chat message, an incident-tracker comment, and
    a webhook body are three different renderings of the same investigation,
    and pre-rendering here would force all three to be the same one.
    """

    state: AgentState
    diagnosis: Diagnosis

    @property
    def run_id(self) -> str:
        """Return the investigation this report is for."""
        return self.state.run_id


@runtime_checkable
class DeliveryDestination(Protocol):
    """Somewhere a finished investigation is shipped to."""

    @property
    def name(self) -> str:
        """Return the name this destination is recorded under."""

    async def deliver(self, payload: DeliveryPayload) -> str:
        """Ship ``payload`` and return a reference to what was created."""


__all__ = [
    "NO_CATALOGUE",
    "NO_RECENT_INCIDENTS",
    "UNRANKED",
    "CapabilityRanker",
    "Catalogue",
    "CatalogueResolver",
    "DeliveryDestination",
    "DeliveryPayload",
    "FixedCatalogueResolver",
    "InMemoryIncidentIndex",
    "IncidentIndex",
    "IncidentSignals",
    "NoIncidentIndex",
    "RankedCapability",
    "StaticCatalogue",
    "UnrankedCapabilities",
]
