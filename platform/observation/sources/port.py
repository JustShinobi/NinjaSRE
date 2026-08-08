"""What a source of signals has to be able to do, and nothing more.

The protocol is here rather than in ``integrations/`` for the reason the
discovery one is: tier 3 cannot import tier 2, and the tick is tier 3. An
integration that can report a measurement implements ``SignalReader`` and
declares it like any other capability.

**Nothing here can carry a credential.** ``read`` takes the resources to read
about and a budget. There is no parameter a token fits in and no constructor
argument on the protocol, because the tick does not have one either. An
implementation reaches its provider through ``integrations/_base/client.py``,
which resolves a tenant-scoped handle at the network edge.

**A source declares its interval, and the interval travels on the sample.** A
detector reading a window has the samples and nothing else, so "how often was
this supposed to arrive" has to be on each one — otherwise "it stopped
reporting" is a question the window cannot answer. A source that promises
nothing declares an interval of zero, and an absence detector correctly refuses
to conclude anything from its silence.

**A failed read raises.** Returning no readings would be indistinguishable from
a provider that answered and had nothing to say, and the two produce opposite
verdicts from an absence detector — one is an outage of the source and the other
is an outage of the estate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from config.constants.observation import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MAX_SIGNAL_PAGE_SIZE,
    MIN_POLL_INTERVAL_SECONDS,
)
from core.capability.metadata import SideEffectLevel
from platform.observation.errors import ObservationBoundExceeded
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key


@dataclass(frozen=True, slots=True)
class SignalReading:
    """One measurement a source reports, in the source's own terms.

    Deliberately not a ``Signal``: there is no identity here and no source name,
    because deriving the key is the poller's job and doing it in eighty
    integrations is eighty chances to do it differently.
    """

    name: str
    resource_id: str
    kind: SignalKind = SignalKind.NUMBER
    value: float = 0.0
    state: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)
    #: When the *provider* says the measurement was taken. ``None`` means the
    #: source has no opinion and the poll instant is used, which is honest for a
    #: reading that was computed at call time.
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SignalPage:
    """What one call to a source returned, and what it cost."""

    readings: tuple[SignalReading, ...] = ()
    #: How many provider calls producing this page cost. Reported by the source
    #: because only the source knows whether one page was one request or nine.
    provider_calls: int = 1


@dataclass(frozen=True, slots=True)
class SignalDeclaration:
    """What a source says about itself before it is ever polled.

    The side-effect level is always ``READ`` and the constructor refuses
    anything else. Observation reads: a source that wrote would change the thing
    it is measuring, and there is no deployment in which that is what somebody
    wanted.
    """

    source: str
    #: The signal names this source produces. Declared so a detector naming a
    #: signal nothing emits fails at wiring rather than by never firing.
    signals: tuple[str, ...]
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    #: What the provider will tolerate. Reused from the integration's existing
    #: rate-limit handling rather than being a second budget observation invents.
    rate_limit_per_minute: int = 60
    max_provider_calls: int = 10
    side_effect_level: SideEffectLevel = SideEffectLevel.READ

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("A signal declaration needs the source it belongs to.")
        if not self.signals:
            raise ValueError(
                f"{self.source} declares a signal source and names no signals. A source "
                f"that measures nothing has nothing to declare."
            )
        if self.side_effect_level is not SideEffectLevel.READ:
            raise ValueError(
                f"{self.source} declares a signal source at {self.side_effect_level.value}. "
                f"Observation reads; a source that wrote would change what it measures."
            )
        if self.interval_seconds < MIN_POLL_INTERVAL_SECONDS:
            raise ObservationBoundExceeded(
                parameter=f"{self.source} poll interval",
                requested=self.interval_seconds,
                limit=MIN_POLL_INTERVAL_SECONDS,
                constant="MIN_POLL_INTERVAL_SECONDS",
            )


@dataclass(frozen=True, slots=True)
class PollBudget:
    """What one poll may spend before it stops.

    ``max_readings`` is the page bound rather than a truncation of the estate: a
    source asked about more resources than fit in one page is asked again next
    tick, and nothing is silently dropped.
    """

    max_provider_calls: int = 10
    max_readings: int = MAX_SIGNAL_PAGE_SIZE

    @classmethod
    def for_declaration(cls, declaration: SignalDeclaration) -> PollBudget:
        """Return the budget a source's own declaration narrows to.

        A source may declare fewer calls than the ceiling and never more, so
        this is a minimum and there is no path by which a source widens its own
        budget.
        """
        return cls(max_provider_calls=max(1, declaration.max_provider_calls))


def as_signal(
    reading: SignalReading,
    *,
    source: str,
    interval_seconds: int,
    now: datetime,
) -> Signal:
    """Return ``reading`` as the stored sample, with its identity derived.

    The one place a signal id is made. Derived from the name, the resource, and
    the instant, so a poll that retried writes the same row — which is what
    keeps an average over a window an average over observations rather than over
    deliveries.
    """
    observed_at = reading.observed_at or now
    return Signal(
        signal_id=signal_key(reading.name, reading.resource_id, observed_at),
        name=reading.name,
        resource_id=reading.resource_id,
        source=source,
        kind=reading.kind,
        observed_at=observed_at,
        value=reading.value,
        state=reading.state,
        interval_seconds=interval_seconds,
        labels=dict(reading.labels),
    )


@runtime_checkable
class SignalReader(Protocol):
    """A source of measurements, reached without this package holding a credential."""

    @property
    def declaration(self) -> SignalDeclaration:
        """Return what this source says about itself: signals, interval, bounds."""

    async def read(
        self,
        *,
        resource_ids: tuple[str, ...],
        at: datetime,
        budget: PollBudget,
    ) -> SignalPage:
        """Return this source's measurements for ``resource_ids`` as at ``at``.

        ``at`` is the caller's instant rather than the source's own clock. A
        source that reached for the wall clock would be one a replay could not
        reproduce, and reproducing a firing against stored signals is the whole
        of how a detector is tested.

        Raises whatever the integration's client raises when the provider is
        unreachable. Failing loudly is correct: an empty page and an unreachable
        provider produce opposite verdicts from an absence detector, and only
        one of them is about the estate.
        """


__all__ = [
    "PollBudget",
    "SignalDeclaration",
    "SignalPage",
    "SignalReader",
    "SignalReading",
    "as_signal",
]
