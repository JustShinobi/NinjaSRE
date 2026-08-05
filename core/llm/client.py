"""The one client every provider gets, so nine adapters share one behaviour.

Retry, schema normalisation, the context guard, prompt caching and its uncached
retry, the structured-output ladder, token accounting, and the failure-to-partial
conversion all live here — once. An adapter translates a wire and nothing else.

That is what keeps a tenth provider cheap: it inherits every behaviour the
contract suite already tests, because there is only one implementation of each
and it is this one.

**On the concurrent-turn race.** Everything a retry or an error handler consults
is captured into a local ``_Attempt`` when the request is built: the cache plan,
the normalised tools, the descriptor. Nothing is read back from ``self``. Two
turns sharing this client cannot see each other, and the test that proves it
runs deterministically with no threads at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from typing import Any

from config.constants.llm import (
    CHARACTERS_PER_TOKEN_ESTIMATE,
    LLM_CONTEXT_RESERVE_TOKENS,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_STREAM_TIMEOUT_SECONDS,
)
from core.llm.cache import (
    CachePlan,
    cache_degradation,
    is_cache_marker_rejection,
    plan_prompt_cache,
)
from core.llm.credentials import CredentialResolver, MissingCredentialError, ProviderCredentials
from core.llm.failures import ErrorObservation, FailureClass, ProviderFailure, classify
from core.llm.providers.base import ProviderAdapter, drop_unknown_tool_calls, known_tool_names
from core.llm.registry import ModelDescriptor
from core.llm.retry import DEFAULT_RETRY_POLICY, JitterSource, RetryPolicy
from core.llm.schema import SchemaNormaliser
from core.llm.structured.prose_parsing import parse_prose
from core.llm.structured.tool_coercion import coercion_tool, extract_coerced, strip_coercion_calls
from core.llm.transports import (
    TransportError,
    TransportUnavailableError,
    WireRequest,
    WireTransport,
)
from core.llm.types import (
    AttemptRecord,
    Degradation,
    DegradationKind,
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    StructuredMechanism,
    TokenEstimate,
    ToolSchema,
    merge_degradations,
)
from core.llm.usage import TokenCounts, UsageRecord

#: Awaited between retries. Injected so a test can assert the backoff without
#: spending it; ``asyncio.sleep`` is the only production value.
Sleeper = Any


@dataclass(frozen=True, slots=True)
class _Attempt:
    """Everything one request needs, captured before the first attempt.

    Frozen and local. An error handler reads this, never the client, which is
    what makes two concurrent turns independent by construction rather than by
    a rule someone has to keep following.
    """

    request: InvokeRequest
    descriptor: ModelDescriptor
    cache: CachePlan
    credentials: ProviderCredentials
    payload: Mapping[str, Any]
    routing: Mapping[str, str]
    known_tools: frozenset[str]
    degradations: tuple[Degradation, ...]


class ProviderClient:
    """One provider, one model, and the behaviour every provider shares."""

    def __init__(
        self,
        *,
        adapter: ProviderAdapter,
        descriptor: ModelDescriptor,
        transport: WireTransport,
        credentials: CredentialResolver,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        request_timeout_seconds: float = LLM_REQUEST_TIMEOUT_SECONDS,
        stream_timeout_seconds: float = LLM_STREAM_TIMEOUT_SECONDS,
        jitter: JitterSource | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._adapter = adapter
        self._descriptor = descriptor
        self._transport = transport
        self._credentials = credentials
        self._retry = retry_policy
        self._request_timeout = request_timeout_seconds
        self._stream_timeout = stream_timeout_seconds
        self._jitter = jitter
        self._sleep = sleeper or asyncio.sleep
        self._normaliser = SchemaNormaliser(adapter.dialect)

    # -- identity -------------------------------------------------------------

    @property
    def provider_id(self) -> str:
        """Return the provider this client speaks to."""
        return self._descriptor.provider_id

    @property
    def model_id(self) -> str:
        """Return the model this client is bound to."""
        return self._descriptor.model_id

    @property
    def descriptor(self) -> ModelDescriptor:
        """Return the descriptor this client was built from."""
        return self._descriptor

    # -- request preparation --------------------------------------------------

    def _normalise_tools(self, request: InvokeRequest) -> tuple[ToolSchema, ...]:
        return self._normaliser.normalise_all(request.tools)

    def _context_guard(
        self, request: InvokeRequest
    ) -> tuple[InvokeRequest, tuple[Degradation, ...]]:
        """Refuse a request that cannot fit, before it reaches the provider.

        Refusing here costs nothing. Discovering it at the provider costs a
        round trip, a rejected turn, and — on a provider that charges for the
        attempt — money, all to learn something arithmetic already knew.
        """
        estimate = self.count_tokens(request)
        budget = self._descriptor.context_window - LLM_CONTEXT_RESERVE_TOKENS
        reserved_output = request.max_output_tokens or 0

        if estimate.tokens + reserved_output <= budget:
            return request, ()

        if estimate.tokens > budget:
            raise ProviderFailure(
                FailureClass.CONTEXT_EXCEEDED,
                provider_id=self.provider_id,
                message=(
                    f"request is about {estimate.tokens} tokens against a "
                    f"{self._descriptor.context_window}-token context window"
                ),
            )

        # The prompt fits but the requested output does not. Shrinking the reply
        # keeps the turn, and the caller is told what happened.
        allowed = max(budget - estimate.tokens, 0)
        return (
            replace(request, max_output_tokens=allowed),
            (
                Degradation(
                    DegradationKind.CONTEXT_TRUNCATED,
                    f"output limit reduced to {allowed} tokens to fit the context window",
                ),
            ),
        )

    def _prepare(self, request: InvokeRequest) -> _Attempt:
        """Return everything the attempts will need, resolved once."""
        guarded, guard_degradations = self._context_guard(request)
        normalised = replace(guarded, tools=self._normalise_tools(guarded))

        cache = plan_prompt_cache(normalised, self._descriptor)
        degradations = list(guard_degradations)
        cache_note = cache_degradation(cache)
        if cache_note is not None:
            degradations.append(cache_note)

        if normalised.parallel_tool_calls and not self._descriptor.supports_parallel_tool_calls:
            degradations.append(
                Degradation(
                    DegradationKind.PARALLEL_TOOL_CALLS_SERIALISED,
                    f"{self.provider_id} runs tool calls one at a time for this model",
                )
            )
        if (
            normalised.reasoning_effort is not None
            and not self._descriptor.supports_reasoning_effort
        ):
            degradations.append(
                Degradation(
                    DegradationKind.REASONING_EFFORT_IGNORED,
                    f"{self.model_id} exposes no reasoning-effort control",
                )
            )

        credentials = self._credentials.resolve(self.provider_id)
        payload = self._adapter.build_payload(normalised, self._descriptor, cache)

        return _Attempt(
            request=normalised,
            descriptor=self._descriptor,
            cache=cache,
            credentials=credentials,
            payload=payload,
            routing=self._adapter.routing(credentials, self._descriptor),
            known_tools=known_tool_names(normalised),
            degradations=tuple(degradations),
        )

    def _wire_request(self, attempt: _Attempt, *, payload: Mapping[str, Any]) -> WireRequest:
        return WireRequest(
            provider_id=self.provider_id,
            model_id=self._descriptor.wire_model_id,
            payload=payload,
            credentials=attempt.credentials,
            timeout_seconds=self._request_timeout,
            routing=attempt.routing,
        )

    # -- invoke ---------------------------------------------------------------

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return one completed turn, degraded rather than raised.

        A provider failure never propagates. The caller gets a partial result
        carrying the classification, the attempts, and whatever work survived —
        which is what lets an investigation keep its evidence when a model
        becomes unavailable halfway through.
        """
        try:
            attempt = self._prepare(request)
        except (ProviderFailure, MissingCredentialError) as error:
            return self._failed_result(error, attempts=())

        records: list[AttemptRecord] = []
        payload: Mapping[str, Any] = attempt.payload
        cache_retried = False

        for number in range(1, self._retry.max_attempts + 1):
            try:
                response = await self._transport.send(self._wire_request(attempt, payload=payload))
            except TransportUnavailableError as error:
                records.append(
                    AttemptRecord(
                        number=number, classification=FailureClass.UNKNOWN, detail=str(error)
                    )
                )
                return self._failed_result(
                    ProviderFailure(
                        FailureClass.UNKNOWN,
                        provider_id=self.provider_id,
                        message=str(error),
                    ),
                    attempts=tuple(records),
                    degradations=attempt.degradations,
                )
            except TransportError as error:
                observation = error.observation
                classification = classify(observation)

                if (
                    not cache_retried
                    and attempt.cache.enabled
                    and is_cache_marker_rejection(observation)
                ):
                    # The provider stopped accepting cache markers. Losing the
                    # turn to a performance optimisation is not acceptable, so
                    # the request goes again without them — once.
                    cache_retried = True
                    payload = self._adapter.build_payload(
                        attempt.request, self._descriptor, attempt.cache.without_cache()
                    )
                    attempt = replace(
                        attempt,
                        cache=attempt.cache.without_cache(),
                        degradations=merge_degradations(
                            attempt.degradations,
                            (
                                Degradation(
                                    DegradationKind.PROMPT_CACHE_MARKERS_REJECTED,
                                    "provider rejected the cache markers; retried uncached",
                                ),
                            ),
                        ),
                    )
                    records.append(
                        AttemptRecord(
                            number=number,
                            classification=classification,
                            status_code=observation.status_code,
                            detail="cache markers rejected; retrying uncached",
                        )
                    )
                    continue

                delay = 0.0
                if self._retry.should_retry(classification, number):
                    delay = self._retry.delay_for(
                        number,
                        retry_after_seconds=observation.retry_after_seconds,
                        jitter=self._jitter,
                    )
                records.append(
                    AttemptRecord(
                        number=number,
                        classification=classification,
                        status_code=observation.status_code,
                        delay_seconds=delay,
                        detail=observation.message,
                    )
                )
                if delay == 0.0 and not self._retry.should_retry(classification, number):
                    return self._failed_result(
                        ProviderFailure(
                            classification,
                            provider_id=self.provider_id,
                            message=observation.message,
                            status_code=observation.status_code,
                        ),
                        attempts=tuple(records),
                        degradations=attempt.degradations,
                    )
                await self._sleep(delay)
                continue

            records.append(AttemptRecord(number=number))
            return self._successful_result(attempt, response.payload, tuple(records))

        return self._failed_result(
            ProviderFailure(
                FailureClass.TRANSIENT,
                provider_id=self.provider_id,
                message=f"exhausted {self._retry.max_attempts} attempts",
            ),
            attempts=tuple(records),
            degradations=attempt.degradations,
        )

    def _successful_result(
        self,
        attempt: _Attempt,
        document: Mapping[str, Any],
        records: tuple[AttemptRecord, ...],
    ) -> InvokeResult:
        parsed = self._adapter.parse_response(document, self._descriptor)

        kept, discarded = drop_unknown_tool_calls(parsed.tool_calls, attempt.known_tools)
        degradations = list(attempt.degradations) + list(parsed.degradations)
        if discarded:
            degradations.append(
                Degradation(
                    DegradationKind.UNKNOWN_TOOL_CALL_DISCARDED,
                    f"model called tools that were not sent: {', '.join(sorted(set(discarded)))}",
                )
            )

        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=parsed.text,
            tool_calls=kept,
            finish_reason=parsed.finish_reason,
            usage=self._usage(parsed.tokens),
            structured=parsed.structured,
            degradations=merge_degradations(degradations),
            attempts=records,
        )

    def _failed_result(
        self,
        error: BaseException,
        *,
        attempts: tuple[AttemptRecord, ...],
        degradations: tuple[Degradation, ...] = (),
    ) -> InvokeResult:
        classification = (
            error.classification if isinstance(error, ProviderFailure) else FailureClass.UNKNOWN
        )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            finish_reason=FinishReason.ERROR,
            attempts=attempts,
            degradations=degradations,
            partial=True,
            failure=classification,
            failure_message=str(error),
        )

    def _usage(self, tokens: TokenCounts) -> UsageRecord:
        return UsageRecord.priced(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tokens=tokens,
            pricing=self._descriptor.pricing,
            pricing_as_of=self._descriptor.pricing_as_of,
        )

    # -- structured output ----------------------------------------------------

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return a structured result, by whichever mechanism the provider allows.

        Native first, then tool coercion, then reading the prose. The mechanism
        used is recorded, so the rate at which a provider falls back is a number
        the evaluation suite watches rather than a thing people notice later.
        """
        if self._descriptor.supports_structured_output:
            native = await self.invoke(replace(request, response_schema=schema))
            if native.succeeded:
                parsed = native.structured or parse_prose(native.text)
                if parsed is not None:
                    return replace(
                        native,
                        structured=parsed,
                        structured_mechanism=StructuredMechanism.NATIVE,
                    )
                # Native was requested and produced nothing usable. That is a
                # degradation worth recording, not a reason to stop.
                return await self._coerce_structured(
                    request, schema, reason="native structured output returned no object"
                )
            return native

        return await self._coerce_structured(request, schema, reason="no native JSON mode")

    async def _coerce_structured(
        self,
        request: InvokeRequest,
        schema: Mapping[str, Any],
        *,
        reason: str,
    ) -> InvokeResult:
        """Get structure through a single required tool call, then through prose."""
        coerced_request = replace(
            request,
            tools=(*request.tools, coercion_tool(schema)),
            response_schema=None,
        )
        result = await self.invoke(coerced_request)
        fallback = Degradation(DegradationKind.STRUCTURED_OUTPUT_FALLBACK, reason)

        if not result.succeeded:
            return replace(
                result, degradations=merge_degradations(result.degradations, (fallback,))
            )

        arguments = extract_coerced(result.tool_calls)
        if arguments is not None:
            return replace(
                result,
                tool_calls=strip_coercion_calls(result.tool_calls),
                structured=arguments,
                structured_mechanism=StructuredMechanism.TOOL_COERCION,
                degradations=merge_degradations(result.degradations, (fallback,)),
            )

        parsed = parse_prose(result.text)
        prose_note = Degradation(
            DegradationKind.STRUCTURED_OUTPUT_FALLBACK,
            "model answered in prose; the structured result was parsed out of it",
        )
        return replace(
            result,
            tool_calls=strip_coercion_calls(result.tool_calls),
            structured=parsed,
            structured_mechanism=(
                StructuredMechanism.PROSE_PARSING if parsed is not None else None
            ),
            degradations=merge_degradations(result.degradations, (fallback, prose_note)),
        )

    # -- streaming ------------------------------------------------------------

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Yield events for one streamed turn.

        A stream is not retried. Partial output has already reached the caller,
        and replaying the turn would duplicate it; the failure is yielded as an
        event so the caller decides what to do with what it already has.
        """
        try:
            attempt = self._prepare(request)
        except (ProviderFailure, MissingCredentialError) as error:
            classification = (
                error.classification if isinstance(error, ProviderFailure) else FailureClass.UNKNOWN
            )
            yield StreamEvent(kind=StreamEventKind.ERROR, failure=classification, detail=str(error))
            return

        wire = replace(
            self._wire_request(attempt, payload=attempt.payload),
            timeout_seconds=self._stream_timeout,
        )

        try:
            async for chunk in self._transport.stream(wire):
                for event in self._adapter.parse_stream_chunk(chunk):
                    yield event
        except TransportError as error:
            observation = error.observation
            yield StreamEvent(
                kind=StreamEventKind.ERROR,
                failure=classify(observation),
                detail=observation.message,
            )

    # -- accounting -----------------------------------------------------------

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return the token cost of ``request``, always flagged as an estimate.

        A provider's own tokeniser is authoritative and reaching it costs a
        round trip, which is the wrong trade for a guard that runs before every
        call. So this is a character-count estimate, it says so, and the
        context reserve absorbs the error.
        """
        characters = len(request.system or "")
        for message in request.messages:
            characters += len(message.text)
            for call in message.tool_calls:
                characters += len(call.name) + len(str(dict(call.arguments)))
            for result in message.tool_results:
                characters += len(result.content) + len(result.name)
        for tool in request.tools:
            characters += len(tool.name) + len(tool.description) + len(str(dict(tool.parameters)))

        return TokenEstimate(
            tokens=characters // CHARACTERS_PER_TOKEN_ESTIMATE,
            estimated=True,
        )

    def observe_error_document(
        self, document: Mapping[str, Any], status_code: int | None
    ) -> ErrorObservation:
        """Return the neutral reading of a provider error document.

        Exposed for ``preflight`` and for a caller replaying a recorded failure;
        the invoke path reaches it through the transport.
        """
        return self._adapter.observe_error(document, status_code)


__all__ = ["ProviderClient"]
