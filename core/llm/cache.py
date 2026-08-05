"""Prompt-cache placement, and the one uncached retry when markers are rejected.

Caching is a prefix match: the marker goes at the end of the longest stable
prefix, and any byte that changes before it invalidates everything after. In an
investigation the stable prefix is the system prompt and the tool definitions —
both fixed for the whole run — and the volatile part is the evidence accumulating
in the messages. So the plan is: mark the end of the tool block, and mark the
end of the conversation so far.

The rejection retry exists because cache markers fail *late*. A provider that
has stopped accepting a marker returns a 400, and without a retry the turn is
lost to a performance optimisation. One retry, without markers, and the turn
completes — with the degradation recorded, so a provider that has silently
dropped cache support shows up as a number rather than as a mystery.

The shared-client race this module used to be part of is gone by construction:
:class:`CachePlan` is built from the request and travels with it, so a handler
reacting to one turn's rejection cannot change what another turn already sent.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.llm.failures import ErrorObservation, FailureClass, classify
from core.llm.registry import ModelDescriptor
from core.llm.types import Degradation, DegradationKind, InvokeRequest

#: Providers cap the number of cache breakpoints per request. Four is the
#: smallest cap among the providers that support caching at all, so planning to
#: it keeps one plan valid everywhere.
MAX_CACHE_BREAKPOINTS = 4

#: Below roughly this many characters there is no prefix worth caching, and the
#: write premium is paid for nothing. Providers state the bound in tokens and
#: silently decline rather than erroring, so this is deliberately conservative.
MIN_CACHEABLE_PREFIX_CHARS = 2_048

#: Markers a provider rejects with prose rather than a code. Matched only after
#: the failure has already been classified as a rejected schema or an
#: unclassifiable 400 — a rate limit that happens to mention "cache_control"
#: must not send the caller down the uncached path.
_CACHE_REJECTION_MARKERS = (
    "cache_control",
    "cachecontrol",
    "cache control",
    "prompt caching",
    "cachepoint",
    "cached_content",
    "ephemeral",
)


@dataclass(frozen=True, slots=True)
class CachePlan:
    """Where to place cache markers for one request.

    Built once, from the request, and carried with it. Nothing reads it back
    from client state, which is what makes two concurrent turns independent.
    """

    enabled: bool = False
    #: Mark the end of the system prompt and tool block — the part of the
    #: prefix that does not change for the whole investigation.
    mark_system: bool = False
    #: Mark the end of the conversation so far, so the next turn reads
    #: everything this one wrote.
    mark_last_message: bool = False
    reason: str = ""

    @property
    def breakpoints(self) -> int:
        """Return how many markers this plan places."""
        return int(self.mark_system) + int(self.mark_last_message)

    def without_cache(self) -> CachePlan:
        """Return the same plan with every marker removed, for the retry."""
        return CachePlan(enabled=False, reason="markers rejected by the provider")


def _stable_prefix_size(request: InvokeRequest) -> int:
    """Return the character size of the part of the request that will not change."""
    size = len(request.system or "")
    for tool in request.tools:
        size += len(tool.name) + len(tool.description) + len(str(tool.parameters))
    return size


def plan_prompt_cache(request: InvokeRequest, descriptor: ModelDescriptor) -> CachePlan:
    """Return the cache plan for one request.

    Returns a disabled plan, with the reason recorded, whenever caching would
    not pay: the caller did not ask, the model does not support it, or the
    stable prefix is too small for a provider to cache at all.
    """
    if not request.prompt_cache:
        return CachePlan(reason="not requested")
    if not descriptor.supports_prompt_cache:
        return CachePlan(reason=f"{descriptor.provider_id} does not support prompt caching")
    if _stable_prefix_size(request) < MIN_CACHEABLE_PREFIX_CHARS:
        return CachePlan(reason="stable prefix is below the minimum cacheable size")

    return CachePlan(
        enabled=True,
        mark_system=bool(request.system or request.tools),
        mark_last_message=bool(request.messages),
    )


def is_cache_marker_rejection(observation: ErrorObservation) -> bool:
    """Return whether a failure looks like the provider refusing cache markers.

    Deliberately narrow. It fires only for a failure already classified as a
    rejected schema or an unclassified bad request, and only when the provider
    named something cache-related. A broader rule would retry uncached on
    failures that have nothing to do with caching, which doubles the cost of
    every genuine 400.
    """
    classification = classify(observation)
    if classification not in {FailureClass.SCHEMA_REJECTED, FailureClass.UNKNOWN}:
        return False
    if observation.status_code not in {400, 422}:
        return False

    haystack = f"{observation.message} {observation.error_code or ''}".lower()
    return any(marker in haystack for marker in _CACHE_REJECTION_MARKERS)


def cache_degradation(plan: CachePlan) -> Degradation | None:
    """Return the degradation to record when caching was asked for and not used.

    ``None`` when caching was never requested — a plan disabled for that reason
    carries no ``reason`` and is not a degradation, it is the default.
    """
    if plan.enabled or plan.reason in {"", "not requested"}:
        return None
    return Degradation(DegradationKind.PROMPT_CACHE_UNAVAILABLE, plan.reason)


__all__ = [
    "MAX_CACHE_BREAKPOINTS",
    "MIN_CACHEABLE_PREFIX_CHARS",
    "CachePlan",
    "cache_degradation",
    "is_cache_marker_rejection",
    "plan_prompt_cache",
]
