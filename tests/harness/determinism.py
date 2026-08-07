"""What has to be pinned before two runs of one scenario are comparable.

SC-002 asks for an identical trajectory across two runs, and that is a claim
about *configuration* before it is a claim about the model. Everything a
request can vary by has to be nailed down first, or the suite is measuring
sampling noise and reporting it as a capability change.

This repository's ``InvokeRequest`` deliberately carries no temperature and no
seed: sampling parameters are a provider-level configuration, not something a
caller sets per turn, and inventing fields for them here would put a knob in
the type every provider then has to interpret differently. So the profile below
is in two halves.

**The half this layer can enforce** is real and is applied: prompt caching off,
one fixed reasoning effort, one fixed clock. A cached prefix can change what a
provider returns for an identical prompt, and reasoning effort changes how much
thinking happens — both are per-request fields, and both are pinned.

**The half it can only declare** — temperature, top-p, seed — travels in the
request metadata, where a provider that accepts them passes them on, and is
recorded on every verdict so a reader can see what a run was configured with.

And when the provider will not cooperate at all, ``offline`` removes it from
the picture: a recorded transcript is deterministic by construction, which is
why SC-002 is asserted there as well as here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from config.constants.investigation import DEFAULT_REASONING_EFFORT
from core.llm.types import (
    InvokeRequest,
    InvokeResult,
    ReasoningEffort,
    StreamEvent,
    TokenEstimate,
)


@dataclass(frozen=True, slots=True)
class DeterministicProfile:
    """The configuration a reproducible run is made under.

    Recorded on every verdict rather than assumed, because "the score moved"
    and "the score moved because somebody raised the temperature" are different
    findings and only one of them is about the agent.
    """

    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 20260807
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    prompt_cache: bool = False

    def as_metadata(self) -> dict[str, str]:
        """Return the profile as request metadata a provider may forward."""
        return {
            "temperature": str(self.temperature),
            "top_p": str(self.top_p),
            "seed": str(self.seed),
        }

    def to_record(self) -> dict[str, Any]:
        """Return the profile as it appears on a verdict record."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "reasoning_effort": self.reasoning_effort,
            "prompt_cache": self.prompt_cache,
        }


#: The profile every scenario run uses. One, deliberately: a suite whose
#: scenarios ran under different configurations would produce a number that is
#: an average over configurations rather than a measurement of anything.
DETERMINISTIC: Final = DeterministicProfile()


def pin(request: InvokeRequest, profile: DeterministicProfile = DETERMINISTIC) -> InvokeRequest:
    """Return ``request`` with everything this layer can pin, pinned."""
    metadata: dict[str, str] = {**dict(request.metadata), **profile.as_metadata()}
    return replace(
        request,
        prompt_cache=profile.prompt_cache,
        reasoning_effort=ReasoningEffort(profile.reasoning_effort),
        metadata=metadata,
    )


@dataclass(slots=True)
class DeterministicClient:
    """A provider client with the reproducible configuration applied.

    A wrapper rather than a constructor argument on the real client, because a
    scenario run has to be able to state "this is how the run was configured"
    without the provider layer growing a mode it only has for the suite.
    """

    inner: Any
    profile: DeterministicProfile = DETERMINISTIC
    #: Every request as it left, so a test can assert what was pinned rather
    #: than assert that a wrapper exists.
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""
        return str(self.inner.provider_id)

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""
        return str(self.inner.model_id)

    @property
    def deterministic(self) -> bool:
        """Return that this client pins its configuration."""
        return True

    def _pinned(self, request: InvokeRequest) -> InvokeRequest:
        pinned = pin(request, self.profile)
        self.requests.append(pinned)
        return pinned

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the result of one turn, made under the pinned configuration."""
        result: InvokeResult = await self.inner.invoke(self._pinned(request))
        return result

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Return an iterator of events for one turn, under the pinned configuration."""
        events: AsyncIterator[StreamEvent] = self.inner.stream(self._pinned(request))
        return events

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result, made under the pinned configuration."""
        result: InvokeResult = await self.inner.invoke_structured(self._pinned(request), schema)
        return result

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the token cost of ``request``."""
        estimate: TokenEstimate = self.inner.count_tokens(request)
        return estimate


def is_deterministic(client: Any) -> bool:
    """Return whether ``client`` pins its own configuration.

    A declared property rather than an ``isinstance`` check, for the same
    reason the runtime guard reads ``is_canonical``: a check that matched a
    class would pass the day somebody wrapped one.
    """
    return bool(getattr(client, "deterministic", False))


__all__ = [
    "DETERMINISTIC",
    "DeterministicClient",
    "DeterministicProfile",
    "is_deterministic",
    "pin",
]
