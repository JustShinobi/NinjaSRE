"""What a vendor call raises, classified so the agent can act on it.

An investigation that gets "request failed" learns nothing. It cannot decide
whether to try the other region, wait and retry, ask a human, or give up and say
so — and a loop that cannot decide will do the same wrong thing on every
incident.

So every failure below the base client arrives as one of a closed set of
reasons, and each maps onto the capability taxonomy the loop already reasons
about. The mapping is here rather than at each call site because a capability
author choosing a classification per exception is a capability author
classifying inconsistently, and the loop's behaviour would then depend on which
integration it happened to call.

**A proxy refusal keeps its own reason alongside the client one.** "Datadog is
not configured for this team" and "Datadog returned a 401" both stop the call,
but the first is an operator action and the second is a key problem, and
``proxy_reason`` is what preserves the difference all the way up to the trace.

**There are two vocabularies here, and both earn their place.**
``IntegrationErrorReason`` is the fine-grained one: ten members, because an
operator debugging a failing integration needs "the proxy has no credential for
this team" separated from "the vendor rejected the key". ``ErrorCategory`` is
the coarse one the framework contracts on — the seven names every integration
maps onto, so a suite parameterised over eighty-five vendors can assert that a
403 means the same thing everywhere. Collapsing the two into one enum would
force a choice between an operator-useful message and a catalogue-wide
assertion, and the whole point of having both is that neither has to lose.
"""

from __future__ import annotations

from enum import StrEnum

from core.capability.result import CapabilityError, CapabilityErrorClass
from platform.credentials.proxy.errors import ProxyError, ProxyErrorReason


class ErrorCategory(StrEnum):
    """The shared taxonomy every integration's failures map onto (FR-006).

    Seven names, fixed. They are what the contract suite asserts across the
    whole catalogue and what an investigation's next move is chosen from:
    ``permission`` sends an operator to their vendor's console, ``transient``
    says try again, ``invalid_request`` says the call was wrong and repeating it
    will be wrong again.
    """

    #: The credential is missing, unreadable, or the vendor rejected it.
    AUTH = "auth"
    #: The credential is valid and does not permit this call.
    PERMISSION = "permission"
    #: The vendor says the resource does not exist.
    NOT_FOUND = "not_found"
    #: A rate limit, the vendor's own or the proxy's.
    RATE_LIMITED = "rate_limited"
    #: Something that could plausibly work on the next attempt.
    TRANSIENT = "transient"
    #: The request was malformed, by this client or by its caller.
    INVALID_REQUEST = "invalid_request"
    #: The vendor, or the path to it, is not answering at all.
    UNAVAILABLE = "unavailable"

    @property
    def retryable(self) -> bool:
        """Return whether repeating the same call could plausibly succeed."""
        return self in _RETRYABLE_CATEGORIES


#: The two categories worth repeating. ``unavailable`` is deliberately not one:
#: a proxy or vendor that is down stays down for longer than a retry schedule,
#: and the retry loop above reads the finer-grained reason for the cases —
#: a reachable proxy in front of an unreachable vendor — where it is worth it.
_RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMITED}
)


class IntegrationErrorReason(StrEnum):
    """The closed set of ways a vendor call can fail."""

    #: The proxy could not resolve a credential for this tenant and team.
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    #: The proxy itself is unreachable, or the vendor behind it is.
    PROXY_UNAVAILABLE = "proxy_unavailable"
    #: The request was refused before it left: an undeclared host, a tenant
    #: over its rate limit, an integration with no rule.
    REFUSED = "refused"
    #: The vendor rejected the credential.
    UNAUTHENTICATED = "unauthenticated"
    #: The credential is valid and does not permit this.
    FORBIDDEN = "forbidden"
    #: The vendor says the resource does not exist.
    NOT_FOUND = "not_found"
    #: The vendor's own rate limit.
    RATE_LIMITED = "rate_limited"
    #: The request was malformed, by this client or by its caller.
    INVALID_REQUEST = "invalid_request"
    #: The vendor failed on its own side.
    UPSTREAM_ERROR = "upstream_error"
    #: Nothing came back within the budget.
    TIMEOUT = "timeout"


#: How each reason reaches the model. The loop retries on the retryable classes
#: and routes around the rest, so this table is what turns a vendor's status
#: code into a decision.
_CAPABILITY_CLASSES: dict[IntegrationErrorReason, CapabilityErrorClass] = {
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: CapabilityErrorClass.PERMISSION_DENIED,
    IntegrationErrorReason.PROXY_UNAVAILABLE: CapabilityErrorClass.UNAVAILABLE,
    IntegrationErrorReason.REFUSED: CapabilityErrorClass.PERMISSION_DENIED,
    IntegrationErrorReason.UNAUTHENTICATED: CapabilityErrorClass.PERMISSION_DENIED,
    IntegrationErrorReason.FORBIDDEN: CapabilityErrorClass.PERMISSION_DENIED,
    IntegrationErrorReason.NOT_FOUND: CapabilityErrorClass.NOT_FOUND,
    IntegrationErrorReason.RATE_LIMITED: CapabilityErrorClass.RATE_LIMITED,
    IntegrationErrorReason.INVALID_REQUEST: CapabilityErrorClass.INVALID_ARGUMENTS,
    IntegrationErrorReason.UPSTREAM_ERROR: CapabilityErrorClass.UPSTREAM_ERROR,
    IntegrationErrorReason.TIMEOUT: CapabilityErrorClass.TIMEOUT,
}

#: Each reason's place in the shared taxonomy. Written out rather than derived
#: from the capability class above, because the two answer different questions:
#: the capability class decides how the *loop* reports a failure, and this
#: decides how an *operator* is told to fix it. A credential the proxy cannot
#: resolve reaches the model as "permission denied" and reaches the operator as
#: "auth", and both are right.
_CATEGORIES: dict[IntegrationErrorReason, ErrorCategory] = {
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: ErrorCategory.AUTH,
    IntegrationErrorReason.PROXY_UNAVAILABLE: ErrorCategory.UNAVAILABLE,
    IntegrationErrorReason.REFUSED: ErrorCategory.PERMISSION,
    IntegrationErrorReason.UNAUTHENTICATED: ErrorCategory.AUTH,
    IntegrationErrorReason.FORBIDDEN: ErrorCategory.PERMISSION,
    IntegrationErrorReason.NOT_FOUND: ErrorCategory.NOT_FOUND,
    IntegrationErrorReason.RATE_LIMITED: ErrorCategory.RATE_LIMITED,
    IntegrationErrorReason.INVALID_REQUEST: ErrorCategory.INVALID_REQUEST,
    IntegrationErrorReason.UPSTREAM_ERROR: ErrorCategory.TRANSIENT,
    IntegrationErrorReason.TIMEOUT: ErrorCategory.TRANSIENT,
}

#: A proxy refusal, translated. Rate limiting and unreachability keep their
#: retryable character; everything else the proxy refuses is something an
#: operator has to change, and retrying it burns an iteration.
_PROXY_REASONS: dict[ProxyErrorReason, IntegrationErrorReason] = {
    ProxyErrorReason.MALFORMED_REQUEST: IntegrationErrorReason.INVALID_REQUEST,
    ProxyErrorReason.UNKNOWN_INTEGRATION: IntegrationErrorReason.REFUSED,
    ProxyErrorReason.EGRESS_DENIED: IntegrationErrorReason.REFUSED,
    ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED: (IntegrationErrorReason.CREDENTIAL_UNAVAILABLE),
    ProxyErrorReason.CREDENTIAL_UNREADABLE: IntegrationErrorReason.CREDENTIAL_UNAVAILABLE,
    ProxyErrorReason.CREDENTIAL_EXPIRED: IntegrationErrorReason.CREDENTIAL_UNAVAILABLE,
    ProxyErrorReason.REFRESH_FAILED: IntegrationErrorReason.CREDENTIAL_UNAVAILABLE,
    ProxyErrorReason.RATE_LIMITED: IntegrationErrorReason.RATE_LIMITED,
    ProxyErrorReason.UPSTREAM_UNREACHABLE: IntegrationErrorReason.PROXY_UNAVAILABLE,
}

#: A vendor status, translated. Anything not listed falls to ``UPSTREAM_ERROR``
#: for 5xx and ``INVALID_REQUEST`` for 4xx, which is the least wrong guess for
#: each half.
_STATUS_REASONS: dict[int, IntegrationErrorReason] = {
    400: IntegrationErrorReason.INVALID_REQUEST,
    401: IntegrationErrorReason.UNAUTHENTICATED,
    403: IntegrationErrorReason.FORBIDDEN,
    404: IntegrationErrorReason.NOT_FOUND,
    408: IntegrationErrorReason.TIMEOUT,
    422: IntegrationErrorReason.INVALID_REQUEST,
    429: IntegrationErrorReason.RATE_LIMITED,
    504: IntegrationErrorReason.TIMEOUT,
}


class IntegrationError(Exception):
    """One vendor call that did not produce a usable answer.

    Carries the integration, the classified reason, and — when the proxy was
    what refused — the proxy's own reason. Never carries a credential: the
    message is built from the integration name, the status, and the vendor's
    own words, and a vendor rejecting a key does not echo it back.
    """

    def __init__(
        self,
        message: str,
        *,
        integration: str,
        reason: IntegrationErrorReason,
        status_code: int | None = None,
        detail: str = "",
        proxy_reason: ProxyErrorReason | None = None,
    ) -> None:
        super().__init__(message)
        self.integration = integration
        self.reason = reason
        self.status_code = status_code
        self.detail = detail
        self.proxy_reason = proxy_reason

    @property
    def retryable(self) -> bool:
        """Return whether repeating the same call could plausibly succeed."""
        return _CAPABILITY_CLASSES[self.reason].retryable

    @property
    def category(self) -> ErrorCategory:
        """Return this failure's place in the shared taxonomy (FR-006)."""
        return _CATEGORIES[self.reason]

    def to_capability_error(self) -> CapabilityError:
        """Return this failure as the value the model reads back (FR-012)."""
        return CapabilityError(
            classification=_CAPABILITY_CLASSES[self.reason],
            message=str(self),
            detail=self.detail,
        )

    @classmethod
    def from_proxy(cls, error: ProxyError) -> IntegrationError:
        """Return the client-side form of a proxy refusal."""
        return cls(
            str(error),
            integration=error.integration,
            reason=_PROXY_REASONS.get(error.reason, IntegrationErrorReason.REFUSED),
            detail=error.detail,
            proxy_reason=error.reason,
        )

    @classmethod
    def from_status(
        cls,
        *,
        integration: str,
        status_code: int,
        body: str,
        method: str,
        path: str,
    ) -> IntegrationError:
        """Return the client-side form of a vendor error response.

        ``body`` is truncated by the caller before it reaches here. A vendor
        that answers a bad request with a megabyte of HTML should not put a
        megabyte of HTML in an exception the loop is about to put in a trace.
        """
        return cls(
            f"{integration} answered {status_code} to {method} {path}"
            + (f": {body}" if body else ""),
            integration=integration,
            reason=reason_for_status(status_code),
            status_code=status_code,
            detail=body,
        )


def reason_for_status(status_code: int) -> IntegrationErrorReason:
    """Return the classification for a vendor status code."""
    known = _STATUS_REASONS.get(status_code)
    if known is not None:
        return known
    if status_code >= 500:
        return IntegrationErrorReason.UPSTREAM_ERROR
    return IntegrationErrorReason.INVALID_REQUEST


def category_for(status_code: int) -> ErrorCategory:
    """Return the shared-taxonomy category for a vendor status code.

    The one table. An integration that classified its own statuses would be an
    integration that disagrees with the other eighty-four about what a 403
    means, and the loop's behaviour would then depend on which vendor it
    happened to call.
    """
    return _CATEGORIES[reason_for_status(status_code)]


def categories() -> tuple[ErrorCategory, ...]:
    """Return every category in the shared taxonomy, in declaration order."""
    return tuple(ErrorCategory)


__all__ = [
    "ErrorCategory",
    "IntegrationError",
    "IntegrationErrorReason",
    "categories",
    "category_for",
    "reason_for_status",
]
