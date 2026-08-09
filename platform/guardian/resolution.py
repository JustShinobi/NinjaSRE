"""Turning the shipped set plus a deployment's changes into the detectors that run.

Three inputs and one output. The shipped catalogue says what is worth watching;
the cluster's shape says which of those apply here; the deployment's own
overrides say where the shipped numbers are wrong for this cluster. What comes
out is a list of declarations the ordinary evaluation engine runs, indistinguishable
from ones an operator wrote by hand — which is the property that matters, because
it means the shipped set is not a second detector system.

**An override never edits the shipped set.** FR-016 asks for thresholds
overridable per deployment and per resource without editing what ships, and the
reason is upgrades: an operator who changed a number by editing the catalogue
would lose the change, or block the upgrade, or silently keep an old detector
whose definition has since improved. So the catalogue is read-only and the
override is a separate document that names what it changes.

**Per-resource beats per-deployment.** A datastore that genuinely does run at
ninety per cent is a fact about that datastore, not about every datastore, and
the alternative — turning the detector off deployment-wide — is how one noisy
resource silences the rest.

**An override naming nothing is reported, not ignored.** An override for a
detector that does not exist is almost always a typo in an identifier, and the
symptom of ignoring it is a threshold that never takes effect for a reason
nothing states.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from platform.config_service.schema.policies import DetectorOverrideSettings, GuardianSettings
from platform.guardian.catalogue import SHIPPED_DETECTORS, ShippedDetector
from platform.guardian.topology import ClusterShape
from platform.notifications.models import Severity
from platform.observability.logging import get_logger
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.errors import DetectorInvalid, ObservationError

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedGuardian:
    """What the shipped set resolves to here, and everything that went wrong doing it.

    Both halves, for the same reason the detector configuration returns both: a
    caller that only received the working detectors would have no way to surface
    the broken ones, and an operator whose override never takes effect deserves
    a reason rather than silence.
    """

    #: One entry per active detector, as the evaluation engine's own declaration.
    declarations: tuple[DetectorDeclaration, ...] = ()
    #: The shipped detectors those declarations came from, in the same order, so
    #: a console can put the rationale beside the verdict.
    detectors: tuple[ShippedDetector, ...] = ()
    #: Detectors the shipped set holds that this topology does not activate.
    not_applicable: tuple[str, ...] = ()
    #: One per override that could not be applied, as ``(detector_id, reason)``.
    problems: tuple[tuple[str, str], ...] = ()
    shape: ClusterShape = ClusterShape.SINGLE_NODE
    enabled: bool = False

    def detector_for(self, detector_id: str) -> ShippedDetector | None:
        """Return the shipped detector behind ``detector_id``, or ``None``."""
        for detector in self.detectors:
            if detector.detector_id == detector_id:
                return detector
        return None

    def to_record(self) -> dict[str, Any]:
        """Return the document the API serves and any client renders.

        The whole resolution rather than a list of names, and that is what lets
        the console render the reasoning without computing anything: the
        rationale, the threshold and the remedy all come over the wire beside
        the detector, so a client that decided what a threshold resolved to
        would be a client doing the deployment's job.
        """
        return {
            "enabled": self.enabled,
            "cluster_shape": self.shape.value,
            "cluster_shape_description": self.shape.describe(),
            "detectors": [detector.to_record() for detector in self.detectors],
            "not_applicable": list(self.not_applicable),
            "problems": [
                {"detector_id": detector_id, "reason": reason}
                for detector_id, reason in self.problems
            ],
        }


def resolve(
    settings: GuardianSettings,
    *,
    shape: ClusterShape,
    catalogue: Sequence[ShippedDetector] = SHIPPED_DETECTORS,
) -> ResolvedGuardian:
    """Return the detectors the shipped set runs here, with this deployment's changes.

    A disabled guardian resolves to nothing at all rather than to a set of
    disabled declarations: FR-008 makes the shipped set opt-in, and a deployment
    that never enabled it should not carry forty-six switched-off detectors
    through every listing it renders.
    """
    if not settings.enabled:
        return ResolvedGuardian(shape=shape, enabled=False)

    by_detector, by_resource = _index(settings.overrides)
    active: list[ShippedDetector] = []
    skipped: list[str] = []
    for detector in catalogue:
        if detector.activates_on(shape):
            active.append(detector)
        else:
            skipped.append(detector.detector_id)

    known = {detector.detector_id for detector in catalogue}
    problems: list[tuple[str, str]] = [
        (
            detector_id,
            f"there is no shipped detector called {detector_id!r}; the override changes "
            f"nothing and is almost certainly a mistyped identifier",
        )
        for detector_id in sorted(set(by_detector) | {key[0] for key in by_resource})
        if detector_id not in known
    ]

    declarations: list[DetectorDeclaration] = []
    kept: list[ShippedDetector] = []
    for detector in active:
        override = by_detector.get(detector.detector_id)
        try:
            adjusted = _apply(detector, override) if override is not None else detector
            declaration = adjusted.declaration(
                enabled=override.enabled
                if override is not None and override.enabled is not None
                else True
            )
        except (ObservationError, ValueError) as invalid:
            problems.append((detector.detector_id, str(invalid)))
            logger.warning(
                "guardian.override_invalid",
                detector_id=detector.detector_id,
                reason=str(invalid),
            )
            continue
        declarations.append(declaration)
        kept.append(adjusted)

    return ResolvedGuardian(
        declarations=tuple(declarations),
        detectors=tuple(kept),
        not_applicable=tuple(skipped),
        problems=tuple(problems),
        shape=shape,
        enabled=True,
    )


def threshold_for(
    detector: ShippedDetector,
    settings: GuardianSettings,
    *,
    resource_id: str = "",
) -> float:
    """Return the firing value in force for ``detector`` against ``resource_id``.

    The per-resource override wins over the deployment-wide one, which wins over
    what ships. Resolved here rather than at the comparison so that a console
    showing "the threshold for this datastore" and the evaluator deciding about
    it read the same number from the same function.
    """
    by_detector, by_resource = _index(settings.overrides)
    specific = by_resource.get((detector.detector_id, resource_id)) if resource_id else None
    for override in (specific, by_detector.get(detector.detector_id)):
        if override is not None and override.fire_value is not None:
            return override.fire_value
    return detector.fire_value


def _index(
    overrides: Iterable[DetectorOverrideSettings],
) -> tuple[
    Mapping[str, DetectorOverrideSettings],
    Mapping[tuple[str, str], DetectorOverrideSettings],
]:
    """Return the overrides split into the deployment-wide ones and the per-resource ones."""
    wide: dict[str, DetectorOverrideSettings] = {}
    scoped: dict[tuple[str, str], DetectorOverrideSettings] = {}
    for override in overrides:
        if override.resource_id:
            scoped[(override.detector_id, override.resource_id)] = override
        else:
            wide[override.detector_id] = override
    return wide, scoped


def _apply(detector: ShippedDetector, override: DetectorOverrideSettings) -> ShippedDetector:
    """Return ``detector`` carrying ``override``'s changes, and nothing else changed.

    Raises when the override names a severity that is not one of the levels, so
    a typo is reported rather than silently leaving the shipped severity in
    place — a notification that pages when it was meant not to is the failure
    that costs the most trust.
    """
    fire_value = detector.fire_value
    clear_value = detector.clear_value
    if override.fire_value is not None:
        # A firing value moved without its clear value would leave the clear on
        # the wrong side of it and refuse at construction, which reads to an
        # operator as "my override broke the detector". Carrying the shipped gap
        # across is what makes changing one number a change of one number.
        clear_value = override.fire_value - (detector.fire_value - detector.clear_value)
        fire_value = override.fire_value
    if override.clear_value is not None:
        clear_value = override.clear_value

    return replace(
        detector,
        fire_value=fire_value,
        clear_value=clear_value,
        for_seconds=(
            override.for_seconds if override.for_seconds is not None else detector.for_seconds
        ),
        recovery_seconds=(
            override.recovery_seconds
            if override.recovery_seconds is not None
            else detector.recovery_seconds
        ),
        severity=_severity(detector, override),
    )


def _severity(detector: ShippedDetector, override: DetectorOverrideSettings) -> Severity:
    """Return the severity in force, or raise naming the level nobody declared."""
    if not override.severity:
        return detector.severity
    try:
        return Severity(override.severity)
    except ValueError as unknown:
        raise DetectorInvalid(
            detector.detector_id,
            field="severity",
            reason=(
                f"is {override.severity!r} in this deployment's override, which is not one "
                f"of the declared levels"
            ),
        ) from unknown


__all__ = ["ResolvedGuardian", "resolve", "threshold_for"]
