"""What a probe found out about one model, and what a caller may do with it.

Everything here is a value with a JSON round trip, because a probe is expensive
enough to be worth caching and a cached measurement that cannot be written down
is one that has to be retaken on every process start.

``ModelLimits`` is the part the runtime consumes: two numbers, both measured,
both lower than what the model advertised whenever the model was overstating
itself. The loop reads them and narrows accordingly, which is the difference
between "the transcript overflowed" and "the transcript was compacted".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MIN_TOOL_RESULT_CHARS,
    TOOL_RESULT_CONTEXT_SHARE,
)
from config.constants.llm import CHARACTERS_PER_TOKEN_ESTIMATE
from core.llm.probe.behaviours import REQUIRED_FOR_INVESTIGATION, Behaviour, BehaviourStatus


class ModelUnusableError(RuntimeError):
    """A model that failed a behaviour an investigation needs.

    Raised rather than reported, at the one point where a model is selected for
    an investigation. A model that answers instead of calling the tool does not
    fail at setup; it fails halfway through the first incident, having produced
    a paragraph of plausible prose where an evidence-backed finding should be.
    """


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Which model was probed, precisely enough to notice it changing.

    ``fingerprint`` is whatever the endpoint offers that changes when the weights
    do — a digest, a modification time, a quantisation tag. Empty where the
    endpoint cannot be asked, which is honest: a cache keyed on an identity that
    cannot change is a cache that never invalidates, and saying so beats
    pretending the answer is still current.
    """

    provider_id: str
    model_id: str
    fingerprint: str = ""

    @property
    def slot(self) -> tuple[str, str]:
        """Return the cache slot this identity occupies, fingerprint aside."""
        return (self.provider_id, self.model_id)

    def to_record(self) -> dict[str, str]:
        """Return a JSON-serialisable record of this identity."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ModelIdentity:
        """Return the identity a stored record describes."""
        return cls(
            provider_id=str(record["provider_id"]),
            model_id=str(record["model_id"]),
            fingerprint=str(record.get("fingerprint", "")),
        )


@dataclass(frozen=True, slots=True)
class BehaviourResult:
    """One behaviour, as the model actually performed it."""

    behaviour: Behaviour
    status: BehaviourStatus
    detail: str = ""

    def to_record(self) -> dict[str, str]:
        """Return a JSON-serialisable record of this result."""
        return {
            "behaviour": self.behaviour.value,
            "status": self.status.value,
            "detail": self.detail,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> BehaviourResult:
        """Return the result a stored record describes."""
        return cls(
            behaviour=Behaviour(record["behaviour"]),
            status=BehaviourStatus(record["status"]),
            detail=str(record.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class ModelLimits:
    """The measured bounds a run against this model is held to.

    ``usable_context_tokens`` of zero means nobody measured, and the caller falls
    back to the message-count trigger it used before this feature existed. Zero
    is not "no context": a run held to a limit of nothing would compact on its
    first turn.
    """

    usable_context_tokens: int = 0
    max_tool_schemas: int = MAX_AGENT_TOOL_SCHEMAS

    @property
    def measured(self) -> bool:
        """Return whether a context measurement is behind these limits."""
        return self.usable_context_tokens > 0

    @property
    def tool_result_chars(self) -> int:
        """Return how much of one capability result the model may be shown.

        Zero — meaning "show all of it" — when nobody measured this model. A
        deployment on a frontier model must not start losing the tail of its log
        queries because a mechanism for seven-billion-parameter builds exists,
        and a bound that applied whether or not anyone had measured would do
        exactly that.
        """
        if not self.measured:
            return 0
        share = int(
            self.usable_context_tokens * CHARACTERS_PER_TOKEN_ESTIMATE * TOOL_RESULT_CONTEXT_SHARE
        )
        return max(share, MIN_TOOL_RESULT_CHARS)


#: The limits a deployment that never probed anything runs under. The ceilings
#: this repository already shipped, unchanged — which is what makes the probe an
#: improvement on the default rather than a prerequisite for starting.
UNMEASURED_LIMITS = ModelLimits()


@dataclass(frozen=True, slots=True)
class ModelProbe:
    """Everything one probe learned about one model."""

    identity: ModelIdentity
    behaviours: tuple[BehaviourResult, ...] = ()
    usable_context_tokens: int = 0
    advertised_context_tokens: int = 0
    max_tool_schemas: int = MAX_AGENT_TOOL_SCHEMAS
    probed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def status_of(self, behaviour: Behaviour) -> BehaviourStatus:
        """Return how ``behaviour`` came out, or ``SKIPPED`` if it never ran."""
        for result in self.behaviours:
            if result.behaviour is behaviour:
                return result.status
        return BehaviourStatus.SKIPPED

    @property
    def unusable_because(self) -> tuple[str, ...]:
        """Return one sentence per required behaviour this model failed.

        Named by behaviour rather than by number, because the operator's next
        action differs entirely between "it will not call tools" and "its context
        is too small", and a single "unusable" tells them which of those to guess.
        """
        return tuple(
            f"{self.identity.model_id} failed {behaviour.value}: {self._detail(behaviour)}"
            for behaviour in sorted(REQUIRED_FOR_INVESTIGATION, key=lambda item: item.value)
            if self.status_of(behaviour) is BehaviourStatus.FAILED
        )

    def _detail(self, behaviour: Behaviour) -> str:
        for result in self.behaviours:
            if result.behaviour is behaviour:
                return result.detail or "no detail recorded"
        return "not probed"

    @property
    def usable_for_investigation(self) -> bool:
        """Return whether this model may be selected to run an investigation."""
        return not self.unusable_because

    @property
    def limits(self) -> ModelLimits:
        """Return the bounds the runtime should hold a run against this model to."""
        return ModelLimits(
            usable_context_tokens=self.usable_context_tokens,
            max_tool_schemas=min(self.max_tool_schemas, MAX_AGENT_TOOL_SCHEMAS),
        )

    @property
    def overstated_context(self) -> bool:
        """Return whether the model's usable context is below its advertised one."""
        return 0 < self.usable_context_tokens < self.advertised_context_tokens

    def render(self) -> str:
        """Return the report as text, for a surface to print verbatim."""
        lines = [
            f"provider: {self.identity.provider_id}",
            f"model:    {self.identity.model_id}",
            "",
        ]
        width = max((len(result.behaviour.value) for result in self.behaviours), default=0)
        for result in self.behaviours:
            suffix = f"  {result.detail}" if result.detail else ""
            lines.append(
                f"  [{result.status.value:>8}] {result.behaviour.value.ljust(width)}{suffix}"
            )
        lines.append("")
        lines.append(
            f"  usable context: {self.usable_context_tokens} tokens "
            f"(advertised {self.advertised_context_tokens})"
            + ("  — the advertised figure is wrong" if self.overstated_context else "")
        )
        lines.append(f"  tool schemas per turn: {self.limits.max_tool_schemas}")
        lines.append("")
        lines.extend(f"  unusable: {reason}" for reason in self.unusable_because)
        if self.usable_for_investigation:
            lines.append("  usable for an investigation")
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of the whole probe."""
        return {
            "identity": self.identity.to_record(),
            "behaviours": [result.to_record() for result in self.behaviours],
            "usable_context_tokens": self.usable_context_tokens,
            "advertised_context_tokens": self.advertised_context_tokens,
            "max_tool_schemas": self.max_tool_schemas,
            "probed_at": self.probed_at.isoformat(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ModelProbe:
        """Return the probe a stored record describes."""
        return cls(
            identity=ModelIdentity.from_record(record["identity"]),
            behaviours=tuple(
                BehaviourResult.from_record(item) for item in record.get("behaviours") or ()
            ),
            usable_context_tokens=int(record.get("usable_context_tokens", 0)),
            advertised_context_tokens=int(record.get("advertised_context_tokens", 0)),
            max_tool_schemas=int(record.get("max_tool_schemas", MAX_AGENT_TOOL_SCHEMAS)),
            probed_at=datetime.fromisoformat(str(record["probed_at"])),
        )


@dataclass(frozen=True, slots=True)
class EndpointProbe:
    """Every model one endpoint serves, and which of them could run a run.

    Per model rather than per provider, which is the whole difference between
    this and ``preflight``. An operator pointing a deployment at their own model
    server has pulled four or five things; "the provider works" tells them
    nothing about which of those to configure, and "these two tool call, this one
    does not, and that one's usable context is a third of what its card says" is
    a sentence they can act on in one step.
    """

    provider_id: str
    models: tuple[ModelProbe, ...] = ()

    @property
    def usable(self) -> tuple[ModelProbe, ...]:
        """Return the models an investigation could be run on."""
        return tuple(probe for probe in self.models if probe.usable_for_investigation)

    @property
    def unusable(self) -> tuple[ModelProbe, ...]:
        """Return the models that failed a required behaviour."""
        return tuple(probe for probe in self.models if not probe.usable_for_investigation)

    def probe_of(self, model_id: str) -> ModelProbe | None:
        """Return what was measured about one model, or ``None``."""
        return next((probe for probe in self.models if probe.identity.model_id == model_id), None)

    def render(self) -> str:
        """Return the report a surface prints when somebody asks what will work."""
        lines = [f"provider: {self.provider_id}", ""]
        for probe in self.models:
            mark = "usable  " if probe.usable_for_investigation else "unusable"
            lines.append(f"  [{mark}] {probe.identity.model_id}")
            lines.append(
                f"             usable context {probe.usable_context_tokens} tokens"
                + (
                    f" (advertised {probe.advertised_context_tokens})"
                    if probe.overstated_context
                    else ""
                )
                + f", {probe.limits.max_tool_schemas} tool schemas per turn"
            )
            lines.extend(f"             {reason}" for reason in probe.unusable_because)
        lines.append("")
        lines.append(f"{len(self.usable)} of {len(self.models)} model(s) can run an investigation")
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of the whole endpoint."""
        return {
            "provider_id": self.provider_id,
            "models": [probe.to_record() for probe in self.models],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EndpointProbe:
        """Return the endpoint report a stored record describes."""
        return cls(
            provider_id=str(record["provider_id"]),
            models=tuple(ModelProbe.from_record(item) for item in record.get("models") or ()),
        )


def require_usable(probe: ModelProbe) -> ModelProbe:
    """Return ``probe`` if its model may run an investigation, else raise.

    The one gate between a probe result and a model selection, so "a model that
    fails a required behaviour must not be selectable" is a property of calling
    this rather than a rule every caller has to remember.

    Raises:
        ModelUnusableError: naming every required behaviour the model failed.
    """
    if probe.usable_for_investigation:
        return probe
    raise ModelUnusableError("; ".join(probe.unusable_because))


__all__ = [
    "UNMEASURED_LIMITS",
    "BehaviourResult",
    "EndpointProbe",
    "ModelIdentity",
    "ModelLimits",
    "ModelProbe",
    "ModelUnusableError",
    "require_usable",
]
