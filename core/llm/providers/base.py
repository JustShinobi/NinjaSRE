"""What every provider adapter is, and the parts none of them should rewrite.

An adapter is two pure functions and a little routing: build a provider-shaped
payload from a neutral request, and read a neutral result back out of a
provider-shaped document. Everything else — retry, normalisation, caching,
accounting, the structured-output ladder, the context guard — lives once in
``core.llm.client`` and is the same for all nine.

That split is what keeps a tenth provider to one file implementing
:class:`ProviderAdapter` plus a registry row: the behaviour it inherits is the
behaviour the contract suite already tests.

Because the functions are pure over documents, a recorded fixture and a live
call are indistinguishable to them. That is why the contract suite can cover
every provider on every pull request without spending a token.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.llm.cache import CachePlan
from core.llm.credentials import ProviderCredentials
from core.llm.failures import ErrorObservation
from core.llm.registry import ModelDescriptor
from core.llm.schema import SchemaDialect, dialect_for
from core.llm.types import (
    Degradation,
    FinishReason,
    InvokeRequest,
    StreamEvent,
    ToolCall,
)
from core.llm.usage import TokenCounts


@dataclass(frozen=True, slots=True)
class ParsedResponse:
    """A provider's response, read into neutral terms."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: FinishReason = FinishReason.STOP
    tokens: TokenCounts = field(default_factory=TokenCounts)
    structured: Mapping[str, Any] | None = None
    degradations: tuple[Degradation, ...] = ()


@runtime_checkable
class ProviderAdapter(Protocol):
    """The translation between neutral terms and one provider's wire."""

    @property
    def provider_id(self) -> str:
        """Return the provider this adapter speaks for."""

    @property
    def wire_family(self) -> str:
        """Return the wire dialect family, for structured-output field shapes."""

    @property
    def dialect(self) -> SchemaDialect:
        """Return the tool-schema dialect this provider accepts."""

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the provider-shaped body for ``request``.

        ``request`` is already normalised: tools carry this provider's dialect,
        and the context guard has run. The adapter only translates.
        """

    def parse_response(
        self, document: Mapping[str, Any], descriptor: ModelDescriptor
    ) -> ParsedResponse:
        """Return ``document`` read into neutral terms."""

    def parse_stream_chunk(self, chunk: Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        """Return the events one streamed chunk carries, if any."""

    def observe_error(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return what a provider-shaped error document says, in neutral terms."""

    def routing(
        self, credentials: ProviderCredentials, descriptor: ModelDescriptor
    ) -> Mapping[str, str]:
        """Return the out-of-body routing this provider needs."""


class BaseAdapter:
    """The parts every adapter shares.

    A concrete base rather than a mixin: an adapter that forgets to declare its
    dialect should get the strictest one, not an attribute error on the first
    real request.
    """

    provider_identifier: str = ""
    wire: str = "none"

    @property
    def provider_id(self) -> str:
        """Return the provider this adapter speaks for."""
        return self.provider_identifier

    @property
    def wire_family(self) -> str:
        """Return the wire dialect family."""
        return self.wire

    @property
    def dialect(self) -> SchemaDialect:
        """Return the tool-schema dialect this provider accepts."""
        return dialect_for(self.provider_identifier)

    def routing(
        self, credentials: ProviderCredentials, descriptor: ModelDescriptor
    ) -> Mapping[str, str]:
        """Return no out-of-body routing.

        Most providers put everything in the body. The three that do not
        override this.
        """
        return {}

    def parse_stream_chunk(self, chunk: Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        """Return no events.

        Overridden by every adapter that supports streaming; the default keeps a
        provider that does not from having to say so.
        """
        return ()


def coerce_tool_arguments(value: Any) -> dict[str, Any]:
    """Return tool-call arguments as a mapping, whatever the provider sent.

    Providers send arguments as a JSON string, as an object, or — from a
    quantised local model — as a string that is nearly JSON. A tool call whose
    arguments cannot be read is dropped by the caller with the reason recorded;
    guessing at them would run a capability with parameters nobody chose.
    """
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        from core.llm.structured.prose_parsing import parse_prose

        parsed = parse_prose(value)
        if parsed is not None:
            return dict(parsed)
    return {}


def known_tool_names(request: InvokeRequest) -> frozenset[str]:
    """Return the tool names this request actually offered."""
    return frozenset(tool.name for tool in request.tools)


def drop_unknown_tool_calls(
    calls: Sequence[ToolCall], known: frozenset[str]
) -> tuple[tuple[ToolCall, ...], tuple[str, ...]]:
    """Return the calls naming a tool that was sent, and the names that were not.

    A model occasionally calls a tool that is not in the schema set — from an
    earlier turn, or invented. Executing it is not an option, and neither is
    failing the turn: the caller records the discard and keeps the rest.
    """
    kept: list[ToolCall] = []
    discarded: list[str] = []
    for call in calls:
        if call.name in known:
            kept.append(call)
        else:
            discarded.append(call.name)
    return tuple(kept), tuple(discarded)


__all__ = [
    "BaseAdapter",
    "ParsedResponse",
    "ProviderAdapter",
    "coerce_tool_arguments",
    "drop_unknown_tool_calls",
    "known_tool_names",
]
