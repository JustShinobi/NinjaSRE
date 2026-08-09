"""Which of two sources covering the same thing is allowed to produce signals.

When a homelab runs Prometheus with the Proxmox exporter *and* this deployment
polls Proxmox directly, both know how full a datastore is. Two detectors firing
on one condition produce two incidents about one problem, and the operator's
conclusion is that the system is noisy rather than that the datastore is full.

**Precedence is declared per signal, not per source.** A metrics system that has
been scraping a datastore for a year should win on that signal and has nothing
to say about whether a backup job is enabled. Per-source precedence would force
an all-or-nothing choice, and the reason the plan gives is exactly the reference
cluster's: a Prometheus running *inside* the estate it monitors disappears when
the estate does, so the deployment's own polling must keep covering the signals
it can gather directly.

**The loser stops producing rather than producing and being filtered.** A source
that read its provider and had its answer discarded would still have spent the
provider's quota and this deployment's time. Selection happens before the poll.

**Silence is the default, and it favours the deployment's own polling.** An
undeclared duplicate leaves polling in charge, which is what makes enabling a
source additive: FR-023 says enabling one must not silently change which
detectors fire, and a default that handed every signal to the new source would
do exactly that on the first tick after somebody pasted a URL.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from config.constants.observability_bridge import (
    BRIDGE_SOURCE,
    MAX_PRECEDENCE_RULES,
    PRECEDENCE_SOURCE_BRIDGE,
    PRECEDENCE_SOURCE_POLLING,
    PRECEDENCE_SOURCES,
)
from platform.observability.logging import get_logger
from platform.observation.bridge.errors import BridgeBoundExceeded
from platform.observation.sources.port import SignalReader

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PrecedenceRule:
    """One decision about which side of a duplicated coverage produces signals."""

    signal: str
    winner: str
    #: Why this side won, in the operator's terms. Required, because the next
    #: person to wonder why their poller stopped reporting a signal reads this
    #: rather than guessing, and a rule with no reason is one nobody will revise.
    reason: str

    def __post_init__(self) -> None:
        if not self.signal:
            raise ValueError("A precedence rule names the signal it decides.")
        if self.winner not in PRECEDENCE_SOURCES:
            raise ValueError(
                f"precedence for {self.signal!r} names {self.winner!r}; it must be one of "
                f"{', '.join(PRECEDENCE_SOURCES)}. There is no 'both': two sources "
                f"producing one signal is the outcome this rule exists to prevent."
            )
        if not self.reason:
            raise ValueError(
                f"precedence for {self.signal!r} gives no reason. An operator whose "
                f"poller went quiet needs to be able to read why."
            )


@dataclass(frozen=True, slots=True)
class Silenced:
    """One source that will not produce one signal, and what decided that."""

    source: str
    signal: str
    winner: str
    reason: str


@dataclass(frozen=True, slots=True)
class SignalPrecedence:
    """Every declared decision about duplicated coverage."""

    rules: tuple[PrecedenceRule, ...] = ()

    def __post_init__(self) -> None:
        if len(self.rules) > MAX_PRECEDENCE_RULES:
            raise BridgeBoundExceeded(
                parameter="precedence rules",
                requested=len(self.rules),
                limit=MAX_PRECEDENCE_RULES,
                constant="MAX_PRECEDENCE_RULES",
            )
        seen: set[str] = set()
        for rule in self.rules:
            if rule.signal in seen:
                raise ValueError(
                    f"two precedence rules decide {rule.signal!r}. One signal has one "
                    f"winner; two rules is two answers to the question the rule asks."
                )
            seen.add(rule.signal)

    def winner_for(self, signal: str) -> str:
        """Return which side produces ``signal``, declared or by default."""
        for rule in self.rules:
            if rule.signal == signal:
                return rule.winner
        return PRECEDENCE_SOURCE_POLLING

    def reason_for(self, signal: str) -> str:
        """Return why ``signal`` was decided the way it was."""
        for rule in self.rules:
            if rule.signal == signal:
                return rule.reason
        return (
            "no precedence is declared for this signal, so the deployment's own polling "
            "keeps it; enabling a source adds signals rather than taking them over"
        )

    def produces(self, *, signal: str, source: str) -> bool:
        """Return whether ``source`` wins ``signal`` where two sources both cover it.

        A contest, not a licence. A signal only one source declares is produced
        by that source whatever this returns — precedence exists to resolve
        duplication and a deployment with none is not subject to it. ``producers``
        is what applies that rule; this is the predicate underneath.
        """
        side = PRECEDENCE_SOURCE_BRIDGE if source == BRIDGE_SOURCE else PRECEDENCE_SOURCE_POLLING
        return self.winner_for(signal) == side

    def producers(self, readers: Iterable[SignalReader]) -> dict[str, str]:
        """Return the one source that will produce each signal these readers cover.

        Precedence is applied only where a signal is genuinely covered twice.
        Applying it everywhere would mean a signal nobody else produces being
        silenced by a default nobody set, which is a detector that never fires
        for a reason nothing states.
        """
        by_signal: dict[str, list[str]] = {}
        for reader in readers:
            declaration = reader.declaration
            for signal in declaration.signals:
                by_signal.setdefault(signal, []).append(declaration.source)

        resolved: dict[str, str] = {}
        for signal, sources in by_signal.items():
            unique = sorted(set(sources))
            if len(unique) == 1:
                resolved[signal] = unique[0]
                continue
            side = self.winner_for(signal)
            resolved[signal] = next(
                (source for source in unique if self.produces(signal=signal, source=source)),
                unique[0],
            )
            logger.info("bridge.precedence_applied", signal=signal, winner=side)
        return resolved

    def select(
        self, readers: Iterable[SignalReader]
    ) -> tuple[tuple[SignalReader, ...], tuple[Silenced, ...]]:
        """Return the readers that may run, and every signal a reader will not produce.

        A reader whose every declared signal was lost is dropped entirely rather
        than polled and discarded — polling a provider for an answer nobody will
        read spends the operator's rate limit on nothing.
        """
        held = tuple(readers)
        resolved = self.producers(held)
        kept: list[SignalReader] = []
        silenced: list[Silenced] = []

        for reader in held:
            declaration = reader.declaration
            lost = tuple(
                signal
                for signal in declaration.signals
                if resolved.get(signal, declaration.source) != declaration.source
            )
            silenced.extend(
                Silenced(
                    source=declaration.source,
                    signal=signal,
                    winner=self.winner_for(signal),
                    reason=self.reason_for(signal),
                )
                for signal in lost
            )
            if len(lost) == len(declaration.signals):
                logger.info(
                    "bridge.source_silenced",
                    source=declaration.source,
                    signals=len(lost),
                )
                continue
            kept.append(reader)

        return tuple(kept), tuple(silenced)


def duplicated_signals(readers: Sequence[SignalReader]) -> tuple[str, ...]:
    """Return every signal more than one source declares.

    What an operator is asked to decide about. Reported rather than resolved:
    the deployment can see that two sources cover a signal and cannot know which
    of them the operator trusts.
    """
    seen: dict[str, set[str]] = {}
    for reader in readers:
        declaration = reader.declaration
        for signal in declaration.signals:
            seen.setdefault(signal, set()).add(declaration.source)
    return tuple(sorted(signal for signal, sources in seen.items() if len(sources) > 1))


__all__ = ["PrecedenceRule", "SignalPrecedence", "Silenced", "duplicated_signals"]
