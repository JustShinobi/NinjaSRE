"""Which sentence an operator gets when the proxy refuses a verification call."""

from __future__ import annotations

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._verification.diagnostics import refusal_detail

_ADVICE = {
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call before it left: this host is not in the integration's "
        "declared allow-list."
    ),
    IntegrationErrorReason.UNAUTHENTICATED: "Prometheus rejected the credential. Re-issue it.",
}


def _refused(message: str) -> IntegrationError:
    """Return the refusal a vendor verifier catches, carrying the proxy's own words."""
    return IntegrationError(
        message, integration="prometheus", reason=IntegrationErrorReason.REFUSED
    )


def test_a_clear_text_refusal_says_so_instead_of_naming_the_allow_list() -> None:
    """The two refusals share a reason, and only one of them is about hosts.

    A credential about to cross an unencrypted scheme is an egress refusal by
    every fact the proxy checks, so it arrives classified as ``REFUSED`` — the
    same key the allow-list advice was written under, back when the allow-list
    was the only case that reason covered. An operator whose host *is* declared
    and whose problem is the scheme gets sent to check a list they already got
    right.
    """
    error = _refused(
        "'prometheus' would send a stored credential to http://metrics.internal, and http "
        "is never encrypted. Point 'prometheus' at https://metrics.internal instead, or "
        "remove the stored credential and connect it by address only."
    )

    detail = refusal_detail(error, _ADVICE)

    assert "never encrypted" in detail
    assert "allow-list" not in detail


def test_an_allow_list_refusal_names_the_host_and_the_declared_ones() -> None:
    """The proxy's own sentence is more specific than the vendor's for this case too."""
    error = _refused(
        "'prometheus' may not reach 'elsewhere.internal'. Its declared hosts are metrics.internal."
    )

    detail = refusal_detail(error, _ADVICE)

    assert "elsewhere.internal" in detail
    assert "metrics.internal" in detail


def test_every_other_reason_still_gets_the_vendors_own_advice() -> None:
    """Only the vendor knows where its credential is issued, so it keeps that answer."""
    error = IntegrationError(
        "401", integration="prometheus", reason=IntegrationErrorReason.UNAUTHENTICATED
    )

    assert refusal_detail(error, _ADVICE) == _ADVICE[IntegrationErrorReason.UNAUTHENTICATED]
