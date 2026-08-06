"""A clear took effect when the cache is empty, which is checkable even here.

The action has no rollback and it still has a verification. The two are
different questions: "can this be undone" and "did it happen at all", and an
irreversible action is the one where the second matters most.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.remediation.models import Divergence, RemediationAction, StateSnapshot


@dataclass(frozen=True, slots=True)
class EmptyCacheVerifier:
    """Reports a cache that still holds entries after it was told to clear."""

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return a divergence when the cache did not empty."""
        del action, before
        remaining = after.values.get("entries")
        if not remaining:
            return ()
        return (Divergence(field_name="entries", intended=0, actual=remaining),)


verifier = EmptyCacheVerifier()

__all__ = ["EmptyCacheVerifier", "verifier"]
