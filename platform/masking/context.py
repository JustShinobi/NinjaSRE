"""One run's masking state: the policy that applies and the table it fills.

A context is the unit everything else holds. It exists because the two halves
of masking are useless apart — a policy with no mapping cannot be undone, and a
mapping with no policy does not know what to look for — and because binding
them together is what makes "the same token for the whole run" a property of
the object rather than a convention.

``for_provider`` is the only interesting method. It returns a context whose
policy has been resolved against the provider actually being called, **sharing
the same mapping**. Sharing is the point: a run that sends its cheap turns to a
local model and its hard turns to a cloud one still has one table, so a pod
that was masked on turn four is masked as the same token on turn nine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from platform.masking.apply import mask, unmask
from platform.masking.mapping import MaskMapping
from platform.masking.policy import DEFAULT_POLICY, MaskingPolicy


@dataclass(slots=True)
class MaskingContext:
    """The policy and the mapping for one investigation."""

    policy: MaskingPolicy = DEFAULT_POLICY
    mapping: MaskMapping = field(default_factory=MaskMapping)

    def for_provider(self, provider_id: str) -> MaskingContext:
        """Return this context with its policy resolved for ``provider_id``.

        The mapping is shared rather than copied, so a run that talks to two
        providers still issues one token per identifier.
        """
        resolved = self.policy.resolve_for_provider(provider_id)
        if resolved == self.policy:
            return self
        return MaskingContext(policy=resolved, mapping=self.mapping)

    def mask(self, text: str) -> str:
        """Return ``text`` with identifiers replaced, allocating tokens as needed."""
        return mask(text, policy=self.policy, mapping=self.mapping)

    def unmask(self, text: str) -> str:
        """Return ``text`` with this run's tokens replaced by their identifiers."""
        return unmask(text, mapping=self.mapping)

    @property
    def active(self) -> bool:
        """Return whether this context replaces anything."""
        return self.policy.masks_anything

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace may record about masking.

        Counts and a level, never a value and never a token — a trace is read
        by whoever can read the run, and that is a wider set of people than
        those entitled to the identifiers behind it.
        """
        return {
            "level": self.policy.level.value,
            "identifiers_masked": len(self.mapping),
            "by_kind": dict(self.mapping.counts_by_kind()),
        }


__all__ = ["MaskingContext"]
