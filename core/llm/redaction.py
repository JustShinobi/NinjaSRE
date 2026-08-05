"""What an external surface is allowed to learn about a provider failure.

A provider's error message is written for whoever holds the API key. It routinely
contains the request body, an organisation identifier, a deployment name, a
model nobody outside the operator's account should know exists — and, when a
client library is careless, a prefix of the key itself. None of that belongs in
an HTTP response or a chat message.

So there are two renderings of every failure, and they are produced by different
functions rather than by one function with a flag. A flag defaults to the wrong
value exactly once.
"""

from __future__ import annotations

from core.llm.failures import FailureClass, ProviderFailure

#: What each class means to somebody who cannot see the logs. Phrased as what
#: they can do about it, because "an error occurred" wastes the operator's time
#: as surely as leaking the internals would risk their data.
_EXTERNAL_MESSAGES: dict[FailureClass, str] = {
    FailureClass.TRANSIENT: (
        "The language model provider was temporarily unavailable. The request was "
        "retried and did not succeed; try again shortly."
    ),
    FailureClass.RATE_LIMITED: (
        "The language model provider is rate limiting this deployment. The request "
        "was retried and did not succeed; try again shortly."
    ),
    FailureClass.AUTH: (
        "The language model provider rejected this deployment's credentials. An "
        "operator needs to check the provider configuration."
    ),
    FailureClass.SCHEMA_REJECTED: (
        "The language model provider rejected the tool definitions for this "
        "request. This is a configuration defect; it has been recorded."
    ),
    FailureClass.CONTEXT_EXCEEDED: (
        "The request was larger than the configured model's context window. "
        "Narrow the scope of the investigation, or configure a larger model."
    ),
    FailureClass.CONTENT_FILTERED: (
        "The language model provider declined to answer this request under its content policy."
    ),
    FailureClass.MODEL_UNAVAILABLE: (
        "The configured model is not available from this provider. An operator "
        "needs to check the model configuration."
    ),
    FailureClass.UNKNOWN: (
        "The language model provider returned an error that could not be "
        "classified. The details have been recorded server-side."
    ),
}

_FALLBACK_MESSAGE = _EXTERNAL_MESSAGES[FailureClass.UNKNOWN]


def external_message(classification: FailureClass) -> str:
    """Return the sentence an external surface may show for ``classification``.

    Fixed strings, chosen from a closed set. Nothing derived from the provider's
    response reaches this function, so nothing from the provider's response can
    reach a user.
    """
    return _EXTERNAL_MESSAGES.get(classification, _FALLBACK_MESSAGE)


def external_error_summary(error: BaseException) -> str:
    """Return what an external surface may show for an arbitrary exception.

    The exception's *type name* is the most that leaves the host. A type name is
    a fact about NinjaSRE's own code; a message is a fact about the request,
    which is what has to stay inside.
    """
    if isinstance(error, ProviderFailure):
        return external_message(error.classification)
    return f"{_FALLBACK_MESSAGE} ({type(error).__name__})"


def internal_detail(error: BaseException) -> str:
    """Return the full detail, for the server-side log and the run trace only.

    Never call this on a path that reaches an HTTP response, a chat message, or
    any other surface outside the operator's host.
    """
    if isinstance(error, ProviderFailure):
        status = f" status={error.status_code}" if error.status_code is not None else ""
        return (
            f"{error.classification.value}: provider={error.provider_id}{status} "
            f"message={error.message}"
        )
    return f"{type(error).__name__}: {error}"


__all__ = ["external_error_summary", "external_message", "internal_detail"]
