"""What changed about where signals come from when a source was enabled.

FR-023 is a short sentence with a large consequence: enabling a source must not
silently change which detectors fire. Not "must not change" — change is the
point — but must not do it *silently*, because an operator who pastes a
Prometheus URL and finds three detectors behaving differently the next morning
has no way to connect the two.

There are two kinds of change and they are reported apart.

**Added** signals are ones nothing was producing before. A detector reading one
of them was reading nothing and firing nothing, so enabling the source turned a
dead detector on. That is additive and is the ordinary case.

**Taken over** signals are ones something was already producing and a precedence
rule has now handed to the other side. The same detector now fires on different
numbers, gathered differently, at a different cadence. It is a real change to
what the deployment concludes and it only ever happens because somebody declared
it — the default hands nothing over.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from platform.observation.bridge.precedence import SignalPrecedence
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.sources.port import SignalReader


@dataclass(frozen=True, slots=True)
class ProvenanceReport:
    """Which signals changed hands, and which are new."""

    added: tuple[str, ...] = ()
    taken_over: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()

    @property
    def visible(self) -> bool:
        """Return whether anything at all changed about where signals come from."""
        return bool(self.added or self.taken_over)

    @property
    def summary(self) -> str:
        """Return the paragraph shown when a source is enabled."""
        parts: list[str] = []
        if self.added:
            parts.append(
                f"{len(self.added)} signal(s) are now produced that nothing produced "
                f"before: {', '.join(self.added)}"
            )
        if self.taken_over:
            parts.append(
                f"{len(self.taken_over)} signal(s) changed source by declared "
                f"precedence: {', '.join(self.taken_over)}. The detectors reading them "
                f"now read different numbers, gathered differently"
            )
        if self.unchanged:
            parts.append(f"unchanged: {', '.join(self.unchanged)}")
        return "; ".join(parts) or "nothing changed about where signals come from"

    def detectors_affected(self, detectors: Iterable[DetectorDeclaration]) -> tuple[str, ...]:
        """Return the detectors whose signal changed hands.

        Only the taken-over half. A detector reading a newly added signal was
        firing on nothing before and is not *changed* by having something to
        read — it is started, which is what enabling a source is for.
        """
        moved = set(self.taken_over)
        return tuple(
            sorted(detector.detector_id for detector in detectors if detector.signal in moved)
        )


def provenance_change(
    *,
    before: Sequence[SignalReader],
    after: Sequence[SignalReader],
    precedence: SignalPrecedence,
) -> ProvenanceReport:
    """Return what enabling or disabling sources did to where signals come from.

    Computed from the declarations and the precedence rules rather than from
    observed samples: an operator has to be able to see this *before* the next
    tick, and a report that needed a tick's worth of data would arrive after the
    change it describes.
    """
    was = precedence.producers(before)
    now = precedence.producers(after)

    added = tuple(sorted(signal for signal in now if signal not in was))
    taken_over = tuple(
        sorted(signal for signal, source in now.items() if was.get(signal, source) != source)
    )
    unchanged = tuple(
        sorted(signal for signal, source in now.items() if signal in was and was[signal] == source)
    )
    return ProvenanceReport(added=added, taken_over=taken_over, unchanged=unchanged)


__all__ = ["ProvenanceReport", "provenance_change"]
