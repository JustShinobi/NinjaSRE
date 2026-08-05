"""Nothing a provider said reaches a surface outside the operator's host.

The failure mode this guards against is not hypothetical. A provider's 400
routinely echoes the request body, and a request body holds the incident's
evidence — hostnames, log lines, occasionally a value that should never have
been in a prompt. An HTTP error response is the last place any of that belongs.
"""

from __future__ import annotations

import pytest

from core.llm.credentials import ProviderCredentials
from core.llm.failures import FailureClass, ProviderFailure
from core.llm.redaction import external_error_summary, external_message, internal_detail

pytestmark = pytest.mark.unit

#: Everything an external surface must never repeat: the account, the payload,
#: the deployment, and the key.
_SECRETS = (
    "sk-live-4a91f2c8",
    "org-acme-production",
    "checkout-db.internal.acme",
    "SELECT * FROM payment_methods",
    "prod-eu-west-1-deployment",
)

_LEAKY_MESSAGE = (
    f"Invalid API key {_SECRETS[0]} for organisation {_SECRETS[1]} while calling "
    f"deployment {_SECRETS[4]}; request body was: "
    f'{{"messages":[{{"content":"{_SECRETS[3]} on {_SECRETS[2]}"}}]}}'
)


@pytest.mark.parametrize("classification", list(FailureClass))
def test_every_class_has_an_external_sentence(classification: FailureClass) -> None:
    message = external_message(classification)
    assert message
    assert message[0].isupper()


@pytest.mark.parametrize("classification", list(FailureClass))
def test_the_external_sentence_is_fixed_not_derived(classification: FailureClass) -> None:
    """Two failures of the same class read identically, however different they were."""
    first = ProviderFailure(
        classification, provider_id="anthropic", message=_LEAKY_MESSAGE, status_code=401
    )
    second = ProviderFailure(
        classification, provider_id="openai", message="something else entirely", status_code=500
    )

    assert external_error_summary(first) == external_error_summary(second)


@pytest.mark.parametrize("secret", _SECRETS)
def test_no_provider_detail_survives_into_the_external_summary(secret: str) -> None:
    failure = ProviderFailure(
        FailureClass.AUTH, provider_id="openai", message=_LEAKY_MESSAGE, status_code=401
    )

    assert secret not in external_error_summary(failure)


def test_an_arbitrary_exception_leaks_only_its_type_name() -> None:
    class DatabaseConnectionError(RuntimeError):
        """A stand-in for anything unexpected reaching the boundary."""

    summary = external_error_summary(DatabaseConnectionError(_LEAKY_MESSAGE))

    assert "DatabaseConnectionError" in summary
    for secret in _SECRETS:
        assert secret not in summary


def test_the_internal_detail_keeps_everything() -> None:
    """Redaction is about the boundary, not about losing the diagnosis."""
    failure = ProviderFailure(
        FailureClass.AUTH, provider_id="openai", message=_LEAKY_MESSAGE, status_code=401
    )

    detail = internal_detail(failure)

    assert _SECRETS[0] in detail
    assert "openai" in detail
    assert "401" in detail


def test_credentials_never_print_their_values() -> None:
    """``repr`` reaches logs, tracebacks, and test output. A secret escapes once."""
    credentials = ProviderCredentials("openai", {"api_key": _SECRETS[0], "base_url": "https://x"})

    for rendered in (repr(credentials), str(credentials), f"{credentials}"):
        assert _SECRETS[0] not in rendered
        assert "api_key" in rendered


def test_credentials_in_a_formatted_message_still_hide_their_values() -> None:
    credentials = ProviderCredentials("anthropic", {"api_key": _SECRETS[0]})

    assert _SECRETS[0] not in f"resolved {credentials} for the run"
