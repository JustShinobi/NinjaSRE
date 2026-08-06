"""A restart worked when the instances are different ones, not when they exist.

The comparison other capabilities can share does not fit here: the intended
state of a restart is "not what was there", which is the one shape a
field-by-field equality check cannot express.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.remediation.models import Divergence, RemediationAction, StateSnapshot


@dataclass(frozen=True, slots=True)
class RestartVerifier:
    """Reports the instances that survived a restart that should have replaced them."""

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return a divergence for every instance that is still the old one."""
        del action
        previous = set(before.sub_targets)
        survivors = sorted(previous & set(after.sub_targets))
        if not survivors:
            return ()
        return (
            Divergence(
                field_name="instances",
                intended="every instance replaced",
                actual=f"{len(survivors)} still running: {', '.join(survivors)}",
            ),
        )


verifier = RestartVerifier()

__all__ = ["RestartVerifier", "verifier"]
