"""Turning a team's configuration into detectors, and refusing the ones that lie.

FR-006 asks that a team be able to add a detector without new code. That means
the declaration comes out of the hierarchical config service, inherits down the
tree like every other setting, and is validated before anything evaluates it.

The conversion is one function and it is deliberately unforgiving. A detector
whose clear value sits on the wrong side of its firing value would clear the
instant it opened; a state transition with no target state would never fire. The
config schema catches what can be checked one field at a time; this catches the
rest, because a detector that was silently skipped is indistinguishable from an
estate with nothing wrong — which is the failure mode the whole feature exists
to remove.

**Errors are collected, not raised on the first one.** An operator who fixed one
detector and then discovered a second problem in the same document would have to
save four times to find four mistakes. ``read`` returns the detectors that are
valid alongside the reasons the others are not, so the deployment keeps watching
with the ones that work.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.observation import MAX_DETECTORS
from platform.config_service.schema.policies import DetectorSettings, ObservationPolicySettings
from platform.notifications.models import Severity
from platform.observability.logging import get_logger
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
    GroupingKey,
)
from platform.observation.errors import DetectorInvalid, ObservationError

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedDetectors:
    """What one node's configuration resolved to, and what it got wrong.

    Both halves matter. A caller that only received the valid detectors would
    have no way to surface the invalid ones, and an operator whose detector
    never fires deserves a reason rather than silence.
    """

    detectors: tuple[DetectorDeclaration, ...] = ()
    #: One per detector that could not be built, as ``(detector_id, reason)``.
    problems: tuple[tuple[str, str], ...] = ()
    paused: bool = False
    pause_reason: str = ""

    @property
    def enabled(self) -> tuple[DetectorDeclaration, ...]:
        """Return the detectors that would actually evaluate.

        A global pause empties this without emptying ``detectors``, which is the
        difference FR-021 asks for: detection stops and nothing is
        unconfigured.
        """
        if self.paused:
            return ()
        return tuple(detector for detector in self.detectors if detector.enabled)


def read(settings: ObservationPolicySettings) -> ResolvedDetectors:
    """Return the detectors ``settings`` declares, and the reasons for any it does not."""
    built: list[DetectorDeclaration] = []
    problems: list[tuple[str, str]] = []

    for entry in settings.detectors[:MAX_DETECTORS]:
        try:
            built.append(declaration_of(entry))
        except ObservationError as invalid:
            problems.append((entry.detector_id, str(invalid)))
            logger.warning(
                "observation.detector_invalid",
                detector_id=entry.detector_id,
                reason=str(invalid),
            )

    if len(settings.detectors) > MAX_DETECTORS:
        problems.append(
            (
                "",
                f"{len(settings.detectors)} detectors are declared and {MAX_DETECTORS} is the "
                f"most one deployment may hold; the rest were not loaded",
            )
        )

    return ResolvedDetectors(
        detectors=tuple(built),
        problems=tuple(problems),
        paused=settings.paused,
        pause_reason=settings.pause_reason,
    )


def declaration_of(entry: DetectorSettings) -> DetectorDeclaration:
    """Return the declaration ``entry`` describes, or raise naming what is wrong."""
    kind = ConditionKind(entry.kind)
    condition = Condition(
        kind=kind,
        comparison=Comparison(entry.comparison),
        fire_value=entry.fire_value,
        clear_value=entry.clear_value or entry.fire_value,
        silent_after_seconds=entry.silent_after_seconds,
        to_state=entry.to_state,
        from_state=entry.from_state,
    )
    return DetectorDeclaration(
        detector_id=entry.detector_id,
        name=entry.name or entry.detector_id,
        description=entry.description or _implied_description(entry, kind),
        resource_kinds=tuple(entry.resource_kinds),
        signal=entry.signal,
        condition=condition,
        for_seconds=entry.for_seconds,
        recovery_seconds=entry.recovery_seconds,
        severity=_severity(entry),
        grouping_key=GroupingKey(entry.grouping_key),
        enabled=entry.enabled,
        capabilities=tuple(entry.capabilities),
        origin=entry.origin,
        origin_excerpt=entry.origin_excerpt,
    )


def _severity(entry: DetectorSettings) -> Severity:
    """Return the declared severity, or raise naming the field."""
    try:
        return Severity(entry.severity)
    except ValueError as unknown:
        raise DetectorInvalid(
            entry.detector_id,
            field="severity",
            reason=f"is {entry.severity!r}, which is not one of the declared levels",
        ) from unknown


def _implied_description(entry: DetectorSettings, kind: ConditionKind) -> str:
    """Return the sentence a detector gets when its author wrote none.

    Generated rather than left empty, because the declaration refuses an empty
    description and refusing a whole detector over a missing sentence would push
    operators towards writing ``"."``. What is generated says what the rule is,
    which is the least useful honest thing — and it reads badly enough that
    somebody replaces it.
    """
    match kind:
        case ConditionKind.THRESHOLD:
            return f"{entry.signal} {entry.comparison} {entry.fire_value:g}"
        case ConditionKind.ABSENCE:
            return f"{entry.signal} has stopped being reported"
        case ConditionKind.RATE_OF_CHANGE:
            return f"{entry.signal} changing {entry.comparison} {entry.fire_value:g} per minute"
        case ConditionKind.STATE_TRANSITION:
            return f"{entry.signal} entered {entry.to_state!r}"


__all__ = ["ResolvedDetectors", "declaration_of", "read"]
