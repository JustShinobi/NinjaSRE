"""Evidence the loop starts with, rather than spends a turn asking for.

An alert from a known source implies a first question. A Kubernetes alert always
wants the workload's events; a log-platform alert always wants the aggregate
before the samples. Letting the model discover that costs an iteration and a
model call to reach a conclusion that was never in doubt — and it costs it on
every investigation from that source, forever.

Seed calls are deterministic by construction: no model call decides them, so two
runs of the same incident start from the same evidence. That is what makes a
trajectory comparison meaningful at the point where it is most sensitive, which
is the beginning.

The catalogue ships empty. Vendors declare their own seeds as their integrations
land, and a team overrides them in configuration; a source with no plan simply
starts cold, which is the behaviour every source had before this module existed.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.agent.runtime_port import SeedCall


@dataclass(frozen=True, slots=True)
class SeedPlan:
    """The calls one alert source implies, in the order they should run."""

    alert_source: str
    calls: tuple[SeedCall, ...] = ()

    def __post_init__(self) -> None:
        if not self.alert_source.strip():
            raise ValueError("a seed plan must name the alert source it applies to")
        object.__setattr__(self, "alert_source", self.alert_source.strip().lower())


@dataclass(frozen=True, slots=True)
class SeedCatalogue:
    """Which deterministic calls run before the model's first turn.

    Matching is exact on a lower-cased source name. Fuzzy matching here would
    make the set of seed calls a run started with depend on how an alert
    happened to be labelled, which is the opposite of deterministic.
    """

    plans: tuple[SeedPlan, ...] = ()

    def for_source(self, alert_source: str) -> tuple[SeedCall, ...]:
        """Return the calls to run for ``alert_source``, empty when none apply."""
        wanted = alert_source.strip().lower()
        if not wanted:
            return ()
        for plan in self.plans:
            if plan.alert_source == wanted:
                return plan.calls
        return ()

    def with_plan(self, plan: SeedPlan) -> SeedCatalogue:
        """Return a catalogue with ``plan`` added, replacing one for the same source."""
        kept = tuple(item for item in self.plans if item.alert_source != plan.alert_source)
        return SeedCatalogue(plans=(*kept, plan))


#: The default: nothing. A source with no plan starts cold.
EMPTY_SEED_CATALOGUE = SeedCatalogue()


__all__ = [
    "EMPTY_SEED_CATALOGUE",
    "SeedCatalogue",
    "SeedPlan",
]
