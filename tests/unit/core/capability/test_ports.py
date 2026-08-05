"""The two ports that let selection run before the features that fill them exist.

Historical effectiveness arrives in a later feature and integration availability
in another. Selection cannot wait for either, so both are ports with a neutral
default: scoring degrades to source and tag matching, which is the baseline the
whole design was measured against, rather than failing.

The neutrality also matters for ablation. A learning mechanism whose
contribution cannot be switched off cannot be measured.
"""

from __future__ import annotations

import pytest

from core.capability.metadata import Requirements
from core.capability.ports import (
    ConfiguredIntegrations,
    EffectivenessProvider,
    IntegrationAvailability,
    NeutralEffectiveness,
    validate_effectiveness,
)

pytestmark = pytest.mark.unit


def test_the_neutral_provider_scores_every_capability_the_same() -> None:
    provider = NeutralEffectiveness()

    assert provider.effectiveness("datadog_log_statistics", alert_source="datadog") == 0.0
    assert provider.effectiveness("never_seen_before", alert_source="pagerduty") == 0.0


def test_the_neutral_provider_satisfies_the_port() -> None:
    assert isinstance(NeutralEffectiveness(), EffectivenessProvider)


def test_effectiveness_is_bounded_so_one_signal_cannot_dominate() -> None:
    """A score outside the unit interval would silently reweight the scorer."""

    class Overconfident:
        def effectiveness(self, capability: str, *, alert_source: str) -> float:
            return 12.0

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        validate_effectiveness(Overconfident().effectiveness("x", alert_source="y"))

    assert (
        validate_effectiveness(NeutralEffectiveness().effectiveness("x", alert_source="y")) == 0.0
    )


def test_configured_integrations_reports_what_a_team_has() -> None:
    availability = ConfiguredIntegrations(integrations=("datadog", "kubernetes"))

    assert availability.is_available("datadog")
    assert not availability.is_available("splunk")


def test_configured_integrations_satisfies_the_port() -> None:
    assert isinstance(ConfiguredIntegrations(integrations=()), IntegrationAvailability)


def test_unmet_requirements_are_reported_by_name() -> None:
    """ "Excluded" without a reason is indistinguishable from "lost"."""
    availability = ConfiguredIntegrations(integrations=("datadog",))

    unmet = availability.unmet(Requirements(integrations=("datadog", "splunk")))

    assert unmet == ("splunk",)


def test_a_capability_requiring_nothing_is_always_available() -> None:
    availability = ConfiguredIntegrations(integrations=())

    assert availability.unmet(Requirements()) == ()


def test_a_sandbox_profile_requirement_is_checked_too() -> None:
    """A capability can be viable in one deployment profile and not another."""
    availability = ConfiguredIntegrations(integrations=(), sandbox_profiles=("restricted",))

    assert availability.unmet(Requirements(sandbox_profiles=("restricted",))) == ()
    assert availability.unmet(Requirements(sandbox_profiles=("privileged",))) == ("privileged",)
