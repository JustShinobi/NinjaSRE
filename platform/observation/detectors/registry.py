"""The detectors a deployment holds, and the two things an operator does to one.

Enable and disable, and a dry run against history. Everything else about a
detector comes from configuration; this is what a *running* deployment offers
on top of the document.

**A detector may not act.** Every capability a detector names is checked against
the catalogue's declared side-effect level when the detector is registered, and
anything above ``read`` is refused there and then. This is the plan's "detection
reads only" and it is enforced against the catalogue rather than by convention,
because a detector that can act is an autonomous actuator with none of the
autonomy policy's controls in front of it — and it would start acting before
anybody had decided that it may.

The catalogue is reached through a protocol rather than imported. The capability
registry is tier 2 and this is tier 3, so a composition root hands the levels
over — the same shape discovery uses for the same reason.

**A dry run fires nothing.** It returns what the detector *would* have concluded
against stored signals, and there is no parameter that turns it into a real
evaluation. An operator testing a threshold against last week must not be able
to page somebody with last week's numbers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from config.constants.observation import MAX_SIGNAL_PAGE_SIZE
from core.capability.metadata import SideEffectLevel
from platform.observability.logging import get_logger
from platform.observation.detectors.conditions import Observation, Verdict, evaluate
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.errors import DetectorMayNotAct, UnknownDetector
from platform.observation.signals import SignalWindow, windows
from platform.persistence.ports.signal_store import Signal, SignalQuery, SignalStore

logger = get_logger(__name__)


@runtime_checkable
class CapabilityLevels(Protocol):
    """What the capability catalogue says about a capability's side effects."""

    def level_of(self, capability: str) -> SideEffectLevel | None:
        """Return ``capability``'s declared side-effect level, or ``None`` if unknown.

        ``None`` is refused by the registry rather than treated as read. A
        capability nobody declared has no level, and defaulting an unknown to
        the safest value is how an undeclared write becomes an allowed one.
        """


@dataclass(frozen=True, slots=True)
class DryRun:
    """What a detector would have concluded, and nothing it did."""

    detector_id: str
    #: One per subject, in identifier order.
    observations: tuple[Observation, ...] = ()

    @property
    def findings(self) -> tuple[Observation, ...]:
        """Return only the observations that would have opened or sustained an incident."""
        return tuple(entry for entry in self.observations if entry.is_finding)

    @property
    def would_fire(self) -> bool:
        """Return whether this detector would have raised anything."""
        return bool(self.findings)


@dataclass(slots=True)
class DetectorRegistry:
    """Every detector this deployment holds, by identifier."""

    detectors: dict[str, DetectorDeclaration] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        declarations: Iterable[DetectorDeclaration],
        *,
        levels: CapabilityLevels | None = None,
    ) -> DetectorRegistry:
        """Return a registry holding ``declarations``, each checked against ``levels``."""
        registry = cls()
        for declaration in declarations:
            registry.register(declaration, levels=levels)
        return registry

    def register(
        self,
        declaration: DetectorDeclaration,
        *,
        levels: CapabilityLevels | None = None,
    ) -> DetectorDeclaration:
        """Store ``declaration`` and return it, refusing one that could act.

        Raises ``DetectorMayNotAct`` when a named capability is declared above
        ``read`` — or is not declared at all, because an unknown level is not a
        safe one.
        """
        if levels is not None:
            for capability in declaration.capabilities:
                level = levels.level_of(capability)
                if level is not SideEffectLevel.READ:
                    raise DetectorMayNotAct(
                        declaration.detector_id,
                        capability=capability,
                        side_effect_level=level.value if level else "undeclared",
                    )
        self.detectors[declaration.detector_id] = declaration
        return declaration

    def get(self, detector_id: str) -> DetectorDeclaration:
        """Return the detector called ``detector_id``, or raise ``UnknownDetector``."""
        found = self.detectors.get(detector_id)
        if found is None:
            raise UnknownDetector(detector_id)
        return found

    def all(self) -> tuple[DetectorDeclaration, ...]:
        """Return every detector, by identifier."""
        return tuple(self.detectors[key] for key in sorted(self.detectors))

    def enabled(self) -> tuple[DetectorDeclaration, ...]:
        """Return the detectors that would evaluate on the next tick."""
        return tuple(detector for detector in self.all() if detector.enabled)

    def set_enabled(self, detector_id: str, *, enabled: bool) -> DetectorDeclaration:
        """Turn ``detector_id`` on or off in this process and return it.

        In this process. Persisting the change is a configuration write, and
        doing it here would give a deployment two places that decide whether a
        detector runs — after which a restart silently reverts an operator's
        decision or does not, depending on which one they used.
        """
        updated = replace(self.get(detector_id), enabled=enabled)
        self.detectors[detector_id] = updated
        logger.info("observation.detector_toggled", detector_id=detector_id, enabled=enabled)
        return updated

    async def dry_run(
        self,
        detector_id: str,
        signals: SignalStore,
        *,
        now: datetime,
        resource_ids: tuple[str, ...] = (),
    ) -> DryRun:
        """Return what ``detector_id`` would conclude against stored signals.

        Fires nothing, writes nothing, and has no parameter that would make it
        do either. An operator testing a threshold against last week must not be
        able to page somebody with last week's numbers.
        """
        detector = self.get(detector_id)
        opened_at = now - timedelta(seconds=detector.longest_window_seconds)
        samples = await signals.window(
            SignalQuery(
                names=(detector.signal,),
                resource_ids=resource_ids,
                since=opened_at,
                until=now,
                limit=MAX_SIGNAL_PAGE_SIZE,
            )
        )
        latest = await signals.latest(names=(detector.signal,), resource_ids=resource_ids)

        return DryRun(
            detector_id=detector_id,
            observations=tuple(
                evaluate(detector, window, now=now)
                for window in _windows(samples, latest, opened_at=opened_at, closed_at=now)
            ),
        )


def _windows(
    samples: tuple[Signal, ...],
    latest: tuple[Signal, ...],
    *,
    opened_at: datetime,
    closed_at: datetime,
) -> tuple[SignalWindow, ...]:
    """Return one window per series, silent series included."""
    return windows(samples, opened_at=opened_at, closed_at=closed_at, latest=latest)


__all__ = ["CapabilityLevels", "DetectorRegistry", "DryRun", "Verdict"]
