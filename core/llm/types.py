"""The provider-neutral vocabulary every adapter translates to and from.

Nothing here knows a vendor. A request is built once, in these terms, and each
adapter is responsible for the round trip into its provider's wire shape and
back. That is what makes a tenth provider a new file under ``providers/``
rather than a change to the callers.

``LLMClient`` is the whole surface a caller sees: ``invoke``, ``stream``,
``invoke_structured``, ``count_tokens``. Where a provider cannot do something —
parallel tool calls, prompt caching, a reasoning-effort control — the result
records the degradation rather than quietly behaving differently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from core.llm.failures import FailureClass
from core.llm.usage import UsageRecord


class Role(StrEnum):
    """Who produced a message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ReasoningEffort(StrEnum):
    """How much deliberation to request, where the provider exposes a control."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class FinishReason(StrEnum):
    """Why generation stopped."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    REFUSAL = "refusal"
    ERROR = "error"


class StructuredMechanism(StrEnum):
    """How a structured result was obtained.

    Recorded on every structured call so the evaluation suite can measure how
    often a provider fell back, rather than discovering it during an incident.
    """

    NATIVE = "native"
    TOOL_COERCION = "tool_coercion"
    PROSE_PARSING = "prose_parsing"


class DegradationKind(StrEnum):
    """A capability the caller asked for that the provider could not give."""

    PARALLEL_TOOL_CALLS_SERIALISED = "parallel_tool_calls_serialised"
    REASONING_EFFORT_IGNORED = "reasoning_effort_ignored"
    PROMPT_CACHE_UNAVAILABLE = "prompt_cache_unavailable"
    PROMPT_CACHE_MARKERS_REJECTED = "prompt_cache_markers_rejected"
    STRUCTURED_OUTPUT_FALLBACK = "structured_output_fallback"
    CONTEXT_TRUNCATED = "context_truncated"
    USAGE_ESTIMATED = "usage_estimated"
    UNKNOWN_TOOL_CALL_DISCARDED = "unknown_tool_call_discarded"


@dataclass(frozen=True, slots=True)
class Degradation:
    """One recorded difference between what was asked for and what happened."""

    kind: DegradationKind
    detail: str = ""


class RepairKind(StrEnum):
    """Something the model got wrong that the system handled rather than passed on.

    A repaired call is not a clean call. If repairs were invisible, a model that
    needs three attempts a turn would look exactly like one that needs none, and
    an operator would have no way to learn that changing model would double their
    throughput. So every member here is counted, traced, and exposed.

    Closed, and every member is either an *extraction* — reading what the model
    plainly said out of the shape it said it in — or a *rejection*. Nothing here
    supplies a value the model did not.
    """

    #: The model narrated its call instead of emitting one, in a recognised form.
    TOOL_CALL_EXTRACTED = "tool_call_extracted"
    #: A streamed call arrived in pieces and was put back together.
    FRAGMENTS_REASSEMBLED = "fragments_reassembled"
    #: An argument the capability's schema does not declare. The call did not run.
    UNKNOWN_ARGUMENT_REJECTED = "unknown_argument_rejected"
    #: A required argument the model left out. Nothing was filled in for it.
    MISSING_ARGUMENT_REPORTED = "missing_argument_reported"
    #: The same call twice in one turn; the second was dropped before execution.
    DUPLICATE_CALL_DISCARDED = "duplicate_call_discarded"
    #: Text that looked like a call and could not be read as one.
    NO_TOOL_CALL_FOUND = "no_tool_call_found"
    #: The model asked for the same thing too many turns running and was told.
    REPETITION_BROKEN = "repetition_broken"
    #: A capability result shortened for the model, whole in the trace.
    RESULT_TRUNCATED = "result_truncated"
    #: The transcript was summarised to stay inside the model's usable context.
    TRANSCRIPT_COMPACTED = "transcript_compacted"
    #: Fewer capability schemas were offered than selection had chosen.
    SCHEMAS_NARROWED = "schemas_narrowed"


@dataclass(frozen=True, slots=True)
class Repair:
    """One thing the model got wrong, and what was done about it.

    ``parameter`` is populated where a single argument is at fault, because
    "the call was rejected" and "the call was rejected because ``label_selector``
    is not a parameter of this capability" send an operator to different places.
    """

    kind: RepairKind
    detail: str = ""
    capability: str = ""
    parameter: str = ""

    def to_record(self) -> dict[str, str]:
        """Return a JSON-serialisable record of this repair."""
        return {
            "kind": self.kind.value,
            "detail": self.detail,
            "capability": self.capability,
            "parameter": self.parameter,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Repair:
        """Return the repair a stored record describes."""
        return cls(
            kind=RepairKind(record["kind"]),
            detail=str(record.get("detail", "")),
            capability=str(record.get("capability", "")),
            parameter=str(record.get("parameter", "")),
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model's request to run one tool."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of running one tool, on its way back to the model."""

    call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of the conversation.

    A single shape carries text, tool calls, and tool results because every
    provider packs the three differently and the adapter is the only place that
    should care which.
    """

    role: Role
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """A tool as the caller declares it, before any provider dialect is applied."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class InvokeRequest:
    """One provider-neutral request.

    Everything a retry or an error handler needs is captured here when the
    request is built. Nothing is read back from mutable client state later —
    that is the whole of the concurrent-turn fix, and it is a property of this
    type rather than a rule someone has to remember.
    """

    messages: tuple[Message, ...]
    system: str | None = None
    tools: tuple[ToolSchema, ...] = ()
    max_output_tokens: int | None = None
    reasoning_effort: ReasoningEffort | None = None
    response_schema: Mapping[str, Any] | None = None
    parallel_tool_calls: bool = True
    prompt_cache: bool = False
    stop_sequences: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One attempt at a request, whether or not it succeeded.

    An attempt that never entered the trace did not happen, and a retry nobody
    can see is indistinguishable from a slow provider.
    """

    number: int
    classification: FailureClass | None = None
    status_code: int | None = None
    delay_seconds: float = 0.0
    detail: str = ""


@dataclass(frozen=True, slots=True)
class InvokeResult:
    """What one completed call produced.

    ``partial`` marks a result that a failure cut short. The caller keeps its
    prior work and decides what to do; it never sees an unhandled provider
    exception.
    """

    provider_id: str
    model_id: str
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: FinishReason = FinishReason.STOP
    usage: UsageRecord | None = None
    structured: Mapping[str, Any] | None = None
    structured_mechanism: StructuredMechanism | None = None
    degradations: tuple[Degradation, ...] = ()
    #: What the resilience layer had to do to the model's output to use it.
    #: Empty for a well-behaved model, which is how a caller can assert that the
    #: clean path stayed clean.
    repairs: tuple[Repair, ...] = ()
    attempts: tuple[AttemptRecord, ...] = ()
    partial: bool = False
    failure: FailureClass | None = None
    failure_message: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether the call produced a usable result."""
        return self.failure is None


class StreamEventKind(StrEnum):
    """What a streamed event carries."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    FINISH = "finish"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event from a streamed generation."""

    kind: StreamEventKind
    text: str = ""
    tool_call: ToolCall | None = None
    #: A slice of the argument document, for a provider that streams a tool
    #: call's arguments as text deltas. The pieces are meaningless apart and the
    #: whole is a call, so the neutral shape has to be able to carry a piece —
    #: otherwise reassembly would have to happen inside every adapter that
    #: streams, which is the duplication this layer exists to avoid.
    tool_call_fragment: str = ""
    usage: UsageRecord | None = None
    finish_reason: FinishReason | None = None
    failure: FailureClass | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    """A token count, and whether anyone measured it.

    ``estimated`` is not decoration. A cost computed from an estimate must not
    be presented as a measurement, and the evaluation suite separates the two.
    """

    tokens: int
    estimated: bool


@runtime_checkable
class LLMClient(Protocol):
    """The single surface every provider implements."""

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the result of one completed turn, degraded rather than raised."""

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Return an iterator of events for one streamed turn."""

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a result whose ``structured`` field satisfies ``schema``.

        The mechanism used — native, tool coercion, or prose parsing — is
        recorded on the result.
        """

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the token cost of ``request``, flagged when it is an estimate."""


def merge_degradations(*groups: Sequence[Degradation]) -> tuple[Degradation, ...]:
    """Return the degradations across ``groups``, first occurrence of each kind kept."""
    seen: dict[DegradationKind, Degradation] = {}
    for group in groups:
        for degradation in group:
            seen.setdefault(degradation.kind, degradation)
    return tuple(seen.values())


__all__ = [
    "AttemptRecord",
    "Degradation",
    "DegradationKind",
    "FinishReason",
    "InvokeRequest",
    "InvokeResult",
    "LLMClient",
    "Message",
    "ReasoningEffort",
    "Repair",
    "RepairKind",
    "Role",
    "StreamEvent",
    "StreamEventKind",
    "StructuredMechanism",
    "TokenEstimate",
    "ToolCall",
    "ToolResult",
    "ToolSchema",
    "merge_degradations",
]
