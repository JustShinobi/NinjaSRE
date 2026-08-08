"""What a source of resources has to be able to do, and nothing more.

The protocol is here rather than in ``integrations/`` because tier 3 cannot
import tier 2, and the sweep is tier 3. ``integrations/_base/discovery.py``
re-exports every name below, so an integration author reads the contract beside
the rest of the integration framework and a composition root wires the two
together. There is one definition; the other module is a doorway.

**Nothing here can carry a credential.** ``discover`` takes a mode, a cursor,
and a budget. There is no parameter a token could be passed in, no constructor
argument on the protocol, and no way for the sweep to hand one over — because
the sweep does not have one either. An implementation reaches its provider
through ``integrations/_base/client.py``, which resolves a tenant-scoped handle
at the network edge. A structural test asserts this rather than trusting it.

**Bounds are declared, not requested.** ``DiscoveryDeclaration`` says how often
this source is swept, whether it can answer incrementally, and how many provider
calls one sweep may make. The sweep enforces them; a source cannot raise its own
ceiling, because the ceiling it declares is itself bounded by the constants.

**A page is a page, not a promise.** ``DiscoveryPage.complete`` is how a source
says it has reached the end of the inventory, and it is the *only* thing that
entitles the sweep to conclude anything about what it did not see. A source that
paginated and stopped early returns ``complete=False``, and nothing is marked
absent — which is the difference between an estate and a wrong estate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.estate import (
    DEFAULT_DISCOVERY_INTERVAL_SECONDS,
    MAX_SWEEP_PROVIDER_CALLS,
    MAX_SWEEP_RESOURCES,
    MAX_SWEEP_SECONDS,
    MIN_DISCOVERY_INTERVAL_SECONDS,
)
from core.capability.metadata import SideEffectLevel
from platform.estate.errors import SweepBoundExceeded


class DiscoveryMode(StrEnum):
    """How much of the inventory a sweep is asking for.

    The distinction has one consequence and it is the important one: only a
    ``FULL`` sweep that ran to completion may conclude that a resource it did
    not see is gone. An incremental sweep saw a delta, and a delta says nothing
    about what is missing from it.
    """

    FULL = "full"
    INCREMENTAL = "incremental"


@dataclass(frozen=True, slots=True)
class DiscoveredResource:
    """One thing a source reports, in the source's own terms.

    Deliberately not a ``Resource``: there is no identity here, no health state,
    and no parent identifier — only ``native_id`` and ``parent_native_id``,
    which are what the *provider* calls things. Deriving identity is the
    estate's job and doing it in eighty integrations is eighty chances to do it
    differently.

    ``provider_status`` is the raw string, kept raw. Mapping it into the closed
    health set is a declared mapping the estate applies, not something a source
    decides.
    """

    kind: str
    native_id: str
    display_name: str = ""
    #: What another integration describing the same underlying thing would also
    #: report: a machine UUID, a serial number, a fully-qualified hostname.
    #: Empty when a source has nothing to correlate on, and reconciliation never
    #: matches empty against empty — the absence of a correlator is not one.
    correlation_key: str = ""
    parent_native_id: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)
    labels: tuple[str, ...] = ()
    team_node_id: str | None = None
    provider_status: str = ""
    #: Named observations beyond the status: a fill percentage, a failed unit
    #: count, a last-success timestamp. Values are strings for the reason
    #: ``HealthSignal.value`` is.
    signals: Mapping[str, str] = field(default_factory=dict)
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryPage:
    """What one call to a source returned, and whether there is more.

    ``complete`` and an empty ``cursor`` are not the same statement.
    ``complete=True`` means the source has shown the whole inventory this mode
    covers; an empty cursor merely means there is no bookmark to resume from.
    A source that finished in one call sets both.
    """

    resources: tuple[DiscoveredResource, ...] = ()
    complete: bool = True
    cursor: str = ""
    #: How many provider calls producing this page cost. Reported by the source
    #: because only the source knows whether one page was one request or nine.
    provider_calls: int = 1


@dataclass(frozen=True, slots=True)
class DiscoveryDeclaration:
    """What a source says about itself before it is ever swept.

    Article IX: a capability is declared, with its rate limits and its
    side-effect level. Discovery's level is always ``READ`` and the constructor
    refuses anything else — a discovery that wrote would be a discovery that
    could change the estate it is describing, and there is no configuration in
    which that is what somebody wanted.
    """

    integration: str
    #: The kinds this source emits. Checked against the kind registry when the
    #: source registers, so a typo fails at wiring rather than mid-sweep.
    kinds: tuple[str, ...]
    supports_incremental: bool = False
    interval_seconds: int = DEFAULT_DISCOVERY_INTERVAL_SECONDS
    max_provider_calls: int = MAX_SWEEP_PROVIDER_CALLS
    #: What the provider will tolerate. Reused from the integration's existing
    #: rate-limit handling rather than being a second budget the sweep invents.
    rate_limit_per_minute: int = 60
    side_effect_level: SideEffectLevel = SideEffectLevel.READ

    def __post_init__(self) -> None:
        if not self.integration:
            raise ValueError("A discovery declaration needs the integration it belongs to.")
        if not self.kinds:
            raise ValueError(
                f"{self.integration} declares discovery but names no resource kinds. A source "
                f"that enumerates nothing has nothing to declare."
            )
        if self.side_effect_level is not SideEffectLevel.READ:
            raise ValueError(
                f"{self.integration} declares discovery at {self.side_effect_level.value}. "
                f"Discovery reads; a discovery that wrote would change the estate it describes."
            )
        if self.interval_seconds < MIN_DISCOVERY_INTERVAL_SECONDS:
            raise SweepBoundExceeded(
                parameter=f"{self.integration} discovery interval",
                requested=self.interval_seconds,
                limit=MIN_DISCOVERY_INTERVAL_SECONDS,
                constant="MIN_DISCOVERY_INTERVAL_SECONDS",
            )
        if self.max_provider_calls > MAX_SWEEP_PROVIDER_CALLS:
            raise SweepBoundExceeded(
                parameter=f"{self.integration} provider calls per sweep",
                requested=self.max_provider_calls,
                limit=MAX_SWEEP_PROVIDER_CALLS,
                constant="MAX_SWEEP_PROVIDER_CALLS",
            )


@dataclass(frozen=True, slots=True)
class SweepBudget:
    """What one sweep may spend before it suspends.

    Suspension rather than truncation is the whole point. Ten thousand
    resources arriving on first connection is the case this exists for, and the
    mitigation is that the sweep comes back at its cursor — not that the bound
    is raised until the first connection fits inside it.
    """

    max_seconds: float = MAX_SWEEP_SECONDS
    max_provider_calls: int = MAX_SWEEP_PROVIDER_CALLS
    max_resources: int = MAX_SWEEP_RESOURCES

    @classmethod
    def for_declaration(cls, declaration: DiscoveryDeclaration) -> SweepBudget:
        """Return the budget a source's own declaration narrows to.

        A source may declare *fewer* calls than the ceiling and never more —
        ``DiscoveryDeclaration`` refuses more at construction. So this is a
        minimum, and there is no path by which a source widens its own budget.
        """
        return cls(max_provider_calls=min(declaration.max_provider_calls, MAX_SWEEP_PROVIDER_CALLS))


@runtime_checkable
class ResourceReader(Protocol):
    """A source of resources, reached without this package holding a credential."""

    @property
    def declaration(self) -> DiscoveryDeclaration:
        """Return what this source says about itself: kinds, interval, bounds."""

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the next page of what this source can see.

        Raises whatever the integration's client raises when the provider is
        unreachable. Failing loudly is correct here and returning an empty page
        would be catastrophic: an empty page from a *complete* sweep is what
        marks the entire estate absent.
        """


__all__ = [
    "DiscoveredResource",
    "DiscoveryDeclaration",
    "DiscoveryMode",
    "DiscoveryPage",
    "ResourceReader",
    "SweepBudget",
]
