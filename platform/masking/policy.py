"""How much of an identifier an operator is willing to send, and to whom.

Masking has a cost. Every identifier replaced by a token is a fact the model
reasons about at one remove, and past some point that shows up as a worse
investigation. So the amount of it is a per-team decision with a measured
default rather than a constant somebody picked, and the evaluation suite runs
with each level so the cost is a number instead of an opinion.

The four levels are not four amounts. Three are:

``off``
    Nothing is replaced. Right when the provider is already trusted with the
    operator's infrastructure names — a self-hosted endpoint, an existing data
    processing agreement.

``standard``
    Pods, clusters, namespaces, hostnames, IP addresses, cloud account
    identifiers, and ARNs. The default, because it is the level at which the
    evaluation suite stops being able to measure a quality difference.

``strict``
    Adds service and deployment names, and turns on the operator's own
    patterns. Service names carry meaning the model uses — ``checkout`` failing
    is a different hypothesis from ``batch-reconciler`` failing — so this is the
    level where the trade-off becomes real.

The fourth, ``local_models_exempt``, is a *rule* rather than an amount: behave
as ``standard`` against a provider on somebody else's infrastructure, and as
``off`` against one on the operator's own. It exists because a deployment where
nothing leaves the host has nothing to mask, and masking it anyway spends
investigation quality to buy nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from config.constants.llm import LOCAL_PROVIDERS
from config.constants.security import DEFAULT_MASKING_POLICY, MASKING_POLICY_LEVELS
from platform.patterns import UnsafePatternError, compile_untrusted


class MaskingLevel(StrEnum):
    """How much a team is willing to send to a model it does not host."""

    OFF = "off"
    STANDARD = "standard"
    STRICT = "strict"
    LOCAL_MODELS_EXEMPT = "local_models_exempt"


#: The masking-facing spelling of :class:`platform.patterns.UnsafePatternError`.
#: The same exception object, not a subclass, so a caller catching either name
#: catches both and neither can drift away from the other.
CustomPatternError = UnsafePatternError


@dataclass(frozen=True, slots=True)
class CustomPattern:
    """One operator-supplied identifier shape, named so a rejection can say which."""

    name: str
    pattern: str

    def compile(self) -> re.Pattern[str]:
        """Return the compiled pattern, or raise ``CustomPatternError``.

        Validation lives in ``platform.patterns`` because guardrail rules need
        exactly the same treatment, and a second copy of it is a second copy
        that can be relaxed independently.
        """
        return compile_untrusted(self.name, self.pattern)


@dataclass(frozen=True, slots=True)
class MaskingPolicy:
    """One team's masking configuration.

    Frozen, because ``resolve_for_provider`` returning a *new* policy is what
    keeps ``local_models_exempt`` honest: there is no moment where a policy
    object has been mutated into ``off`` and something else reads it.
    """

    level: MaskingLevel = MaskingLevel(DEFAULT_MASKING_POLICY)
    custom_patterns: tuple[CustomPattern, ...] = field(default=())

    @classmethod
    def from_level(
        cls, level: str, *, custom_patterns: tuple[CustomPattern, ...] = ()
    ) -> MaskingPolicy:
        """Return the policy for ``level``, or raise on a level nobody defined.

        An unrecognised level raises rather than defaulting. Defaulting a typo
        to ``standard`` would be defensible; defaulting it to whatever the enum
        happened to list first would not, and the two are one edit apart.
        """
        if level not in MASKING_POLICY_LEVELS:
            raise ValueError(
                f"unknown masking level {level!r}; expected one of "
                f"{', '.join(MASKING_POLICY_LEVELS)}"
            )
        return cls(level=MaskingLevel(level), custom_patterns=custom_patterns)

    def resolve_for_provider(self, provider_id: str) -> MaskingPolicy:
        """Return the policy that applies to a call against ``provider_id``.

        Only ``local_models_exempt`` resolves to anything else. Resolution
        happens per call rather than per deployment because a deployment may
        route the cheap turns to a local model and the hard ones to a cloud
        provider, and the exemption has to follow the actual destination.
        """
        if self.level is not MaskingLevel.LOCAL_MODELS_EXEMPT:
            return self
        resolved = MaskingLevel.OFF if provider_id in LOCAL_PROVIDERS else MaskingLevel.STANDARD
        return MaskingPolicy(level=resolved, custom_patterns=self.custom_patterns)

    @property
    def masks_anything(self) -> bool:
        """Return whether this policy replaces identifiers at all.

        ``local_models_exempt`` reads as true here because it is unresolved:
        asking an unresolved policy what it does is a question with no answer,
        and answering "nothing" would be the unsafe half of the guess.
        """
        return self.level is not MaskingLevel.OFF

    @property
    def includes_service_names(self) -> bool:
        """Return whether service and deployment names are replaced at this level."""
        return self.level is MaskingLevel.STRICT


#: The policy a deployment gets until the configuration service can resolve a
#: per-team one.
DEFAULT_POLICY = MaskingPolicy()


__all__ = [
    "DEFAULT_POLICY",
    "CustomPattern",
    "CustomPatternError",
    "MaskingLevel",
    "MaskingPolicy",
]
