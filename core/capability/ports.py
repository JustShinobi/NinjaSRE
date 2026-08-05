"""The two things selection needs to know that this feature does not own.

Historical effectiveness belongs to the memory layer and integration
availability to the configuration service, and neither exists yet. Selection
cannot wait for them: an investigation has to choose capabilities today.

So both are ports with a neutral default, and neutral is a precise claim.
``NeutralEffectiveness`` returns the same score for everything, which makes the
effectiveness term contribute nothing and leaves scoring on source and tag
matching — the behaviour the design was measured against before any learning
existed. That is also exactly what the ablation suite needs: a learning
mechanism whose contribution cannot be switched off cannot be measured, and the
switch is substituting this class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.capability.metadata import Requirements


@runtime_checkable
class EffectivenessProvider(Protocol):
    """How well a capability has historically done on incidents like this one."""

    def effectiveness(self, capability: str, *, alert_source: str) -> float:
        """Return a score in ``[0.0, 1.0]``, where ``0.0`` carries no opinion."""


@runtime_checkable
class IntegrationAvailability(Protocol):
    """What a team has actually configured."""

    def is_available(self, name: str) -> bool:
        """Return whether ``name`` is configured and usable for this team."""

    def unmet(self, requirements: Requirements) -> tuple[str, ...]:
        """Return the required names this team does not have, in declared order."""


def validate_effectiveness(score: float) -> float:
    """Return ``score``, or raise if it is outside the unit interval.

    The scorer multiplies this by a weight. A provider returning 12.0 would not
    look like a bug; it would look like one capability being unaccountably
    certain, on every incident, for as long as nobody checked.
    """
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"effectiveness must be between 0.0 and 1.0, got {score!r}")
    return score


@dataclass(frozen=True, slots=True)
class NeutralEffectiveness:
    """The default provider: no history, therefore no opinion."""

    def effectiveness(self, capability: str, *, alert_source: str) -> float:
        """Return ``0.0`` for everything, which removes the term from the score."""
        return 0.0


@dataclass(frozen=True, slots=True)
class ConfiguredIntegrations:
    """Availability answered from a static list, as a team's configuration is."""

    integrations: tuple[str, ...] = ()
    sandbox_profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "integrations", tuple(self.integrations))
        object.__setattr__(self, "sandbox_profiles", tuple(self.sandbox_profiles))

    def is_available(self, name: str) -> bool:
        """Return whether ``name`` is configured, as an integration or a profile."""
        return name in self.integrations or name in self.sandbox_profiles

    def unmet(self, requirements: Requirements) -> tuple[str, ...]:
        """Return the required names this team does not have, in declared order."""
        return tuple(name for name in requirements.names() if not self.is_available(name))


__all__ = [
    "ConfiguredIntegrations",
    "EffectivenessProvider",
    "IntegrationAvailability",
    "NeutralEffectiveness",
    "validate_effectiveness",
]
