"""Reading the target back, because "the API returned 200" is not "it took effect".

The gap this closes is the one that turns a silent partial failure into a
reported success. A control plane accepts a scale to eight replicas and returns
immediately; the scheduler cannot place three of them; the run says the action
succeeded and the incident report says capacity was added. Nothing in the call
path was wrong, and the conclusion was.

So verification is a second read, through the same reader the request used,
compared against what the action said it intended. Three properties make the
comparison worth having.

**Divergence is reported, never repaired.** A verifier that noticed the shortfall
and re-applied the change would be an unapproved second action, and the one it
would take is the one that has already failed once.

**An unreadable target is unverified, not verified.** "We could not read it back"
is its own outcome and reads as one. Collapsing it into "no divergences found"
is how an unreachable control plane produces a clean report.

**The comparison is against the intent, not against the previous state.** A
change that moved the target somewhere neither expected shows up here, where a
before/after difference check would only notice that *something* happened.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from platform.observability.logging import get_logger
from platform.remediation.components import ComponentRegistry
from platform.remediation.models import (
    Divergence,
    RemediationAction,
    StateSnapshot,
    VerificationReport,
    utc_now,
)

_LOG = get_logger(__name__)


def divergences_between(
    intended: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> tuple[Divergence, ...]:
    """Return every field of ``intended`` that ``actual`` does not agree with.

    One-directional on purpose. A target carrying fields the action said nothing
    about is not a divergence — it is a target with more state than this change
    was concerned with, and reporting it would bury the one field that matters
    under everything the control plane happens to return.

    Shared by the capabilities' own verifiers, so "did it take effect" means the
    same comparison for all seven rather than seven slightly different ones.
    """
    return tuple(
        Divergence(field_name=name, intended=expected, actual=actual.get(name))
        for name, expected in sorted(intended.items())
        if actual.get(name) != expected
    )


@dataclass(slots=True)
class OutcomeVerification:
    """Reads the target back after a change and reports how it differs from the intent.

    Holds the registry rather than a verifier, because which comparison is right
    is the capability's knowledge: a restart is verified by pod identities
    having changed, and a scale by a replica count matching. A central verifier
    would have to know both, and would be wrong about the third one somebody
    adds.
    """

    registry: ComponentRegistry
    clock: Callable[[], datetime] = field(default=utc_now)

    async def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        at: datetime | None = None,
    ) -> VerificationReport:
        """Return what the target looks like now against what the action intended."""
        moment = at if at is not None else self.clock()
        components = self.registry.get(action.capability)
        after = await components.reader.read(action, at=moment)

        if not after.known:
            _LOG.warning(
                "remediation.verification_unreadable",
                action_id=action.action_id,
                capability=action.capability,
                target=str(action.target),
            )
            return VerificationReport(
                target=str(action.target),
                verified_at=moment,
                divergences=(
                    Divergence(
                        field_name="state",
                        intended="readable after the change",
                        actual="unreadable",
                    ),
                ),
                observed=after,
            )

        divergences = components.verifier.verify(action, before=before, after=after)
        if divergences:
            _LOG.error(
                "remediation.divergence_detected",
                action_id=action.action_id,
                capability=action.capability,
                target=str(action.target),
                fields=[divergence.field_name for divergence in divergences],
            )
        return VerificationReport(
            target=str(action.target),
            verified_at=moment,
            divergences=divergences,
            observed=after,
        )


__all__ = [
    "OutcomeVerification",
    "divergences_between",
]
