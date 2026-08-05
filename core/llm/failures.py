"""The closed taxonomy every provider failure is sorted into, and the sorting.

Classification and the retry decision live together because they are one
decision. A generic retry decorator would have to be told, at each call site,
which errors are worth repeating — and the answer depends on a provider's
response shape, which is exactly the knowledge this module owns.

The taxonomy is closed. A failure nobody recognises is ``UNKNOWN``, and
``UNKNOWN`` is not retried: repeating a request whose failure nobody understands
turns a rate limit into an outage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from config.constants.llm import RETRYABLE_HTTP_STATUS_CODES


class FailureClass(StrEnum):
    """Why a provider call did not produce a usable result."""

    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    AUTH = "auth"
    SCHEMA_REJECTED = "schema_rejected"
    CONTEXT_EXCEEDED = "context_exceeded"
    CONTENT_FILTERED = "content_filtered"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNKNOWN = "unknown"


#: The only classes worth repeating. Everything else is reported.
RETRYABLE_CLASSES: frozenset[FailureClass] = frozenset(
    {FailureClass.TRANSIENT, FailureClass.RATE_LIMITED}
)

#: Anthropic returns 529 for an overloaded model; it is transient like a 503,
#: and it is outside the shared HTTP set because no other provider uses it.
_OVERLOADED_STATUS = 529

_AUTH_STATUSES = frozenset({401, 403})
_NOT_FOUND_STATUS = 404
_RATE_LIMIT_STATUS = 429
_BAD_REQUEST_STATUSES = frozenset({400, 422})

#: Provider error codes, mapped where the vendors agree with themselves. Codes
#: are matched before free text because a code is a contract and a message is a
#: sentence somebody may reword.
_ERROR_CODES: dict[str, FailureClass] = {
    "authentication_error": FailureClass.AUTH,
    "billing_error": FailureClass.AUTH,
    "permission_error": FailureClass.AUTH,
    "permission_denied": FailureClass.AUTH,
    "invalid_api_key": FailureClass.AUTH,
    "unauthorizedexception": FailureClass.AUTH,
    "accessdeniedexception": FailureClass.AUTH,
    "rate_limit_error": FailureClass.RATE_LIMITED,
    "rate_limit_exceeded": FailureClass.RATE_LIMITED,
    "insufficient_quota": FailureClass.RATE_LIMITED,
    "throttlingexception": FailureClass.RATE_LIMITED,
    "resource_exhausted": FailureClass.RATE_LIMITED,
    "overloaded_error": FailureClass.TRANSIENT,
    "api_error": FailureClass.TRANSIENT,
    "server_error": FailureClass.TRANSIENT,
    "internalservererror": FailureClass.TRANSIENT,
    "serviceunavailableexception": FailureClass.TRANSIENT,
    "unavailable": FailureClass.TRANSIENT,
    "modelstreamerrorexception": FailureClass.TRANSIENT,
    "context_length_exceeded": FailureClass.CONTEXT_EXCEEDED,
    "string_above_max_length": FailureClass.CONTEXT_EXCEEDED,
    "content_filter": FailureClass.CONTENT_FILTERED,
    "content_policy_violation": FailureClass.CONTENT_FILTERED,
    "responsibleaipolicyviolation": FailureClass.CONTENT_FILTERED,
    "blocked_by_safety": FailureClass.CONTENT_FILTERED,
    "model_not_found": FailureClass.MODEL_UNAVAILABLE,
    "not_found_error": FailureClass.MODEL_UNAVAILABLE,
    "resourcenotfoundexception": FailureClass.MODEL_UNAVAILABLE,
    "validationexception": FailureClass.SCHEMA_REJECTED,
    "invalid_function_parameters": FailureClass.SCHEMA_REJECTED,
    "tool_use_failed": FailureClass.SCHEMA_REJECTED,
}

#: Free-text markers, checked only after codes. Ordered most specific first:
#: a context-window message often also contains the word "invalid".
_CONTEXT_MARKERS = (
    "maximum context length",
    "context length exceeded",
    "context window",
    "prompt is too long",
    "too many tokens",
    "input is too long",
    "exceeds the maximum number of tokens",
    "reduce the length of the messages",
)

_SCHEMA_MARKERS = (
    "invalid schema",
    "input_schema",
    "inputschema",
    "unknown field",
    "unsupported keyword",
    "does not support",
    "invalid_function_parameters",
    "tools.",
    "function parameters",
    "response_format",
    "json_schema",
    "additionalproperties",
    "'oneof'",
    "'anyof'",
    "'$ref'",
    "'format'",
)

_CONTENT_MARKERS = (
    "content management policy",
    "content filter",
    "content policy",
    "safety",
    "blocked by",
    "responsible ai",
    "prohibited_content",
)

_AUTH_MARKERS = (
    "api key",
    "authentication",
    "unauthorized",
    "credentials",
    "expired token",
)

_RATE_MARKERS = (
    "rate limit",
    "too many requests",
    "quota",
    "throttl",
)

_MODEL_MARKERS = (
    "model not found",
    "does not exist",
    "unknown model",
    "no such model",
    "is not supported in region",
    "inference profile",
)

#: Transport exceptions arrive with no HTTP response at all. Matching on the
#: exception's type name keeps this module free of vendor imports while still
#: recognising every SDK's timeout and connection errors.
_TRANSIENT_EXCEPTION_MARKERS = (
    "timeout",
    "timedout",
    "connection",
    "connect",
    "unavailable",
    "protocolerror",
    "remotedisconnected",
    "incompleteread",
)


@dataclass(frozen=True, slots=True)
class ErrorObservation:
    """Everything known about one failed call, in provider-neutral terms.

    Adapters build one of these from whatever their provider returned. The
    classification below reads nothing else, so a new provider is a new
    ``observe_error`` and no change here.
    """

    status_code: int | None = None
    error_code: str | None = None
    message: str = ""
    exception_type: str = ""
    retry_after_seconds: float | None = None
    body: dict[str, Any] = field(default_factory=dict)


class ProviderFailure(Exception):
    """A provider call that produced no result, carrying its classification.

    Raised inside ``core/llm/`` only. Callers receive a partial ``InvokeResult``
    instead, and external surfaces receive neither — see
    ``core.llm.redaction``.
    """

    def __init__(
        self,
        classification: FailureClass,
        *,
        provider_id: str,
        message: str,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.provider_id = provider_id
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_retryable(self) -> bool:
        """Return whether repeating the request could plausibly succeed."""
        return self.classification in RETRYABLE_CLASSES


def _match(haystack: str, markers: tuple[str, ...]) -> bool:
    return any(marker in haystack for marker in markers)


def _classify_text(text: str) -> FailureClass | None:
    """Return the class a provider's prose points at, if any.

    Order is the whole of the logic: a context-window message frequently also
    says "invalid request", and a content-filter message frequently also says
    "policy", so the most specific marker set is consulted first.
    """
    if _match(text, _CONTEXT_MARKERS):
        return FailureClass.CONTEXT_EXCEEDED
    if _match(text, _CONTENT_MARKERS):
        return FailureClass.CONTENT_FILTERED
    if _match(text, _SCHEMA_MARKERS):
        return FailureClass.SCHEMA_REJECTED
    if _match(text, _MODEL_MARKERS):
        return FailureClass.MODEL_UNAVAILABLE
    if _match(text, _RATE_MARKERS):
        return FailureClass.RATE_LIMITED
    if _match(text, _AUTH_MARKERS):
        return FailureClass.AUTH
    return None


def _classify_status(status_code: int) -> FailureClass | None:
    """Return the class a status code decides on its own, if it decides one."""
    if status_code in _AUTH_STATUSES:
        return FailureClass.AUTH
    if status_code == _RATE_LIMIT_STATUS:
        return FailureClass.RATE_LIMITED
    if status_code == _NOT_FOUND_STATUS:
        return FailureClass.MODEL_UNAVAILABLE
    if status_code == _OVERLOADED_STATUS or status_code in RETRYABLE_HTTP_STATUS_CODES:
        return FailureClass.TRANSIENT
    return None


def classify(observation: ErrorObservation) -> FailureClass:
    """Return the class ``observation`` belongs to.

    Precedence, and why:

    1. **Error code.** A vendor's code is a contract; its message is prose.
    2. **Status code**, where the status decides on its own — 401 is never
       anything but auth, and 429 is never anything but a rate limit.
    3. **Message text**, which is the only signal a 400 carries.
    4. **Exception type**, for a transport failure that never got a response.
    """
    if observation.error_code:
        mapped = _ERROR_CODES.get(observation.error_code.strip().lower())
        if mapped is not None:
            return mapped

    if observation.status_code is not None:
        decided = _classify_status(observation.status_code)
        if decided is not None:
            return decided

    text = observation.message.strip().lower()
    if text:
        from_text = _classify_text(text)
        if from_text is not None:
            return from_text

    if observation.status_code in _BAD_REQUEST_STATUSES:
        return FailureClass.UNKNOWN

    exception_type = observation.exception_type.strip().lower()
    if exception_type and _match(exception_type, _TRANSIENT_EXCEPTION_MARKERS):
        return FailureClass.TRANSIENT

    return FailureClass.UNKNOWN


__all__ = [
    "RETRYABLE_CLASSES",
    "ErrorObservation",
    "FailureClass",
    "ProviderFailure",
    "classify",
]
