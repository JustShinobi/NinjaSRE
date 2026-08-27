"""A refused certificate is its own refusal, and it says which certificate.

The defect these tests exist to prevent is one line of collapsing: a TLS
failure caught alongside a connection failure, reported as "nothing answered",
and an operator sent to check a network that is fine. So there are two halves
here — the reason is distinguishable from unreachability all the way out, and
each of the three ways trust can fail says its own pair of facts.
"""

from __future__ import annotations

import pytest

from platform.credentials.proxy.app import STATUS_FOR_REASON
from platform.credentials.proxy.errors import (
    CertificateNameMismatch,
    CertificatePinBroken,
    CertificateUntrusted,
    ProxyError,
    ProxyErrorReason,
    UpstreamUnreachable,
    error_from_record,
)
from platform.credentials.proxy.model import ProxyRequest
from platform.persistence.ports import AuditOutcome
from tests.unit.platform.credentials.conftest import (
    CAPABILITY,
    HOST,
    INTEGRATION,
    ORG_ID,
    TEAM_ID,
    URL,
    Harness,
    build_harness,
)

pytestmark = pytest.mark.unit

OBSERVED = "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
EXPECTED = "11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00"

#: The sentence a network failure produces today, and the one no certificate
#: refusal may ever contain.
UNREACHABLE_WORDS = "did not answer"

KEY = "111111111111111111111111"


def request(*, url: str = URL) -> ProxyRequest:
    """Return a proxy request from a capability that holds no credential."""
    return ProxyRequest(
        integration=INTEGRATION,
        org_id=ORG_ID,
        team_id=TEAM_ID,
        capability=CAPABILITY,
        method="GET",
        url=url,
    )


async def _stocked() -> Harness:
    """Return a harness with a credential in the vault, ready to forward."""
    harness = await build_harness()
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": KEY})
    return harness


# -- the reason is its own reason ----------------------------------------------


def test_a_refused_certificate_is_not_an_unreachable_upstream() -> None:
    assert ProxyErrorReason.CERTIFICATE_UNTRUSTED is not ProxyErrorReason.UPSTREAM_UNREACHABLE
    assert (
        CertificateUntrusted("", host=HOST, observed=OBSERVED).reason
        is ProxyErrorReason.CERTIFICATE_UNTRUSTED
    )


def test_all_three_refusals_carry_the_one_reason() -> None:
    reasons = {
        CertificateUntrusted("", host=HOST, observed=OBSERVED).reason,
        CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED).reason,
        CertificateNameMismatch("", host=HOST, certificate_names=("pve01.acme.example",)).reason,
    }

    assert reasons == {ProxyErrorReason.CERTIFICATE_UNTRUSTED}


def test_repeating_a_refused_certificate_call_is_not_worth_an_iteration() -> None:
    assert not ProxyErrorReason.CERTIFICATE_UNTRUSTED.retryable


def test_the_reason_becomes_its_own_status_and_not_the_unreachable_one() -> None:
    status = STATUS_FOR_REASON[ProxyErrorReason.CERTIFICATE_UNTRUSTED]

    assert status != STATUS_FOR_REASON[ProxyErrorReason.UPSTREAM_UNREACHABLE]
    # A precondition of the deployment's own is unmet: nothing declared what to
    # trust at this address. The same class of answer as a credential nobody
    # has configured, which is the status a caller reading only the number has
    # to be led to.
    assert status == STATUS_FOR_REASON[ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED]


def test_the_reason_survives_the_wire_record_it_is_rebuilt_from() -> None:
    original = CertificateUntrusted("", host=HOST, observed=OBSERVED)

    rebuilt = error_from_record(original.to_record())

    assert rebuilt.reason is ProxyErrorReason.CERTIFICATE_UNTRUSTED
    assert OBSERVED in str(rebuilt)


# -- it crosses the engine as itself -------------------------------------------


async def test_the_engine_lets_a_certificate_refusal_through_unrepackaged() -> None:
    harness = await _stocked()
    harness.sender.failures.append(CertificateUntrusted("", host=HOST, observed=OBSERVED))

    with pytest.raises(CertificateUntrusted) as refused:
        await harness.engine.forward(request())

    assert refused.value.reason is ProxyErrorReason.CERTIFICATE_UNTRUSTED
    assert OBSERVED in str(refused.value)


async def test_the_engine_names_the_integration_the_sender_could_not_know() -> None:
    harness = await _stocked()
    harness.sender.failures.append(CertificateUntrusted("", host=HOST, observed=OBSERVED))

    with pytest.raises(ProxyError) as refused:
        await harness.engine.forward(request())

    assert refused.value.integration == INTEGRATION


async def test_a_certificate_refusal_is_audited_as_denied_with_its_own_reason() -> None:
    harness = await _stocked()
    harness.sender.failures.append(CertificateUntrusted("", host=HOST, observed=OBSERVED))

    with pytest.raises(CertificateUntrusted):
        await harness.engine.forward(request())

    events = await harness.audit_events()
    assert events
    latest = events[0]
    assert latest.outcome is AuditOutcome.DENIED
    assert latest.detail["reason"] == ProxyErrorReason.CERTIFICATE_UNTRUSTED.value


# -- the three phrases ----------------------------------------------------------


def test_an_untrusted_certificate_names_what_was_presented_and_what_to_do() -> None:
    refusal = str(CertificateUntrusted("", host=HOST, observed=OBSERVED))

    assert OBSERVED in refusal
    assert HOST in refusal
    assert "pin" in refusal.lower()


def test_a_broken_pin_names_both_fingerprints_and_says_which_is_which() -> None:
    refusal = str(CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED))

    assert EXPECTED in refusal
    assert OBSERVED in refusal
    assert "expected" in refusal.lower()
    assert "observed" in refusal.lower()


def test_a_broken_pin_says_nothing_degraded() -> None:
    refusal = str(
        CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED)
    ).lower()

    assert "system trust store" in refusal


def test_a_name_that_does_not_match_names_the_address_and_the_certificate() -> None:
    refusal = str(
        CertificateNameMismatch("", host="10.20.20.9", certificate_names=("pve01.acme.example",))
    )

    assert "10.20.20.9" in refusal
    assert "pve01.acme.example" in refusal
    # Trusted, and still refused. Saying only "not trusted" here sends an
    # operator to declare trust they have already declared.
    assert "does not name" in refusal.lower()


def test_the_three_phrases_are_three_and_not_one() -> None:
    phrases = {
        str(CertificateUntrusted("", host=HOST, observed=OBSERVED)),
        str(CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED)),
        str(CertificateNameMismatch("", host=HOST, certificate_names=("pve01.acme.example",))),
    }

    assert len(phrases) == 3


# -- and the fourth message stays exactly where it was --------------------------


@pytest.mark.parametrize(
    "refusal",
    [
        CertificateUntrusted("", host=HOST, observed=OBSERVED),
        CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED),
        CertificateNameMismatch("", host=HOST, certificate_names=("pve01.acme.example",)),
    ],
)
def test_no_certificate_refusal_borrows_the_sentence_for_a_silent_host(
    refusal: ProxyError,
) -> None:
    assert UNREACHABLE_WORDS not in str(refusal)


def test_a_host_that_is_silent_still_says_what_it_says_today_and_no_more() -> None:
    unreachable = str(UpstreamUnreachable(INTEGRATION, host=HOST, cause="TimeoutError: "))

    assert UNREACHABLE_WORDS in unreachable
    assert "certificate" not in unreachable.lower()
    assert "fingerprint" not in unreachable.lower()


def test_the_reason_reaches_a_client_as_itself_rather_than_as_a_permission_problem() -> None:
    """A certificate refusal must not arrive as "the vendor refused you".

    ``_PROXY_REASONS`` falls back to ``REFUSED`` for anything it does not list,
    and ``REFUSED`` reads as a permission problem all the way up: it becomes
    ``PERMISSION_DENIED`` to the loop and ``ErrorCategory.PERMISSION`` to a
    permission probe, which would report a certificate nobody trusts as a
    privilege the token lacks.
    """
    from integrations._base.errors import (
        ErrorCategory,
        IntegrationError,
        IntegrationErrorReason,
    )

    translated = IntegrationError.from_proxy(
        CertificateUntrusted(INTEGRATION, host=HOST, observed=OBSERVED)
    )

    assert translated.reason is IntegrationErrorReason.CERTIFICATE_UNTRUSTED
    assert translated.category is not ErrorCategory.PERMISSION
    assert translated.proxy_reason is ProxyErrorReason.CERTIFICATE_UNTRUSTED
    assert OBSERVED in str(translated)


def test_every_proxy_reason_has_an_explicit_translation() -> None:
    """No reason may fall through to the default, which downgrades silently."""
    from integrations._base.errors import _PROXY_REASONS

    assert set(_PROXY_REASONS) == set(ProxyErrorReason)


def test_no_refusal_carries_certificate_material() -> None:
    refusals = [
        str(CertificateUntrusted("", host=HOST, observed=OBSERVED)),
        str(CertificatePinBroken("", host=HOST, expected=(EXPECTED,), observed=OBSERVED)),
        str(CertificateNameMismatch("", host=HOST, certificate_names=("pve01.acme.example",))),
    ]

    for refusal in refusals:
        assert "BEGIN CERTIFICATE" not in refusal
        assert "PRIVATE KEY" not in refusal
