"""Why a resolution failed, in a form the agent can act on (FR-012).

Every failure the proxy can produce carries a closed-set ``reason`` and the name
of the integration. That pairing is what turns a proxy error into a capability
result the model can reason about: "Datadog is not configured for this team" is
something an investigation can route around, and "500" is not.

The reasons are closed for the same argument the provider taxonomy is closed —
a failure nobody classified is a failure nobody handled, and an open set makes
every ``match`` a guess about what else might arrive.

**Nothing here carries a value, a handle's payload, or a request body.** The
detail line names the integration, the host, or the field, because those are
what an operator types into the fix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from platform.credentials.errors import CredentialError


class ProxyErrorReason(StrEnum):
    """The closed set of ways a proxied call can fail before it reaches the vendor."""

    MALFORMED_REQUEST = "malformed_request"
    UNKNOWN_INTEGRATION = "unknown_integration"
    EGRESS_DENIED = "egress_denied"
    CREDENTIAL_NOT_CONFIGURED = "credential_not_configured"
    CREDENTIAL_UNREADABLE = "credential_unreadable"
    CREDENTIAL_EXPIRED = "credential_expired"
    REFRESH_FAILED = "refresh_failed"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNREACHABLE = "upstream_unreachable"
    #: The address answered and this deployment did not trust what it presented.
    #: Its own reason rather than a shade of the one above, because the two lead
    #: an operator to opposite places: one to the network, and one to a decision
    #: nobody has taken yet about a certificate.
    CERTIFICATE_UNTRUSTED = "certificate_untrusted"

    @property
    def retryable(self) -> bool:
        """Return whether repeating the same call could plausibly succeed.

        Only two are. A missing credential stays missing until an operator adds
        it, and an undeclared host stays undeclared until somebody edits the
        integration — retrying either spends an iteration to learn nothing.
        """
        return self in _RETRYABLE_REASONS


_RETRYABLE_REASONS: frozenset[ProxyErrorReason] = frozenset(
    {ProxyErrorReason.RATE_LIMITED, ProxyErrorReason.UPSTREAM_UNREACHABLE}
)


class ProxyError(CredentialError):
    """A proxied call that never reached the vendor, classified.

    ``to_record`` is what crosses the wire and what lands in the audit trail,
    and it is a fixed set of scalar fields on purpose: a free-form payload is
    how a request body — and eventually a credential inside one — ends up in an
    error nobody reads until it is in a bug report.
    """

    reason: ProxyErrorReason = ProxyErrorReason.MALFORMED_REQUEST

    def __init__(self, message: str, *, integration: str, detail: str = "") -> None:
        super().__init__(message)
        self.integration = integration
        self.detail = detail

    def to_record(self) -> dict[str, Any]:
        """Return the structured form: reason, integration, message, detail."""
        return {
            "reason": str(self.reason),
            "integration": self.integration,
            "message": str(self),
            "detail": self.detail,
            "retryable": self.reason.retryable,
        }


class MalformedProxyRequest(ProxyError):
    """The envelope did not parse, or was missing something required."""

    reason = ProxyErrorReason.MALFORMED_REQUEST


class IntegrationNotDeclared(ProxyError):
    """No injection rule exists for this integration.

    Which means there is no declared way for its secret to enter a request and
    no declared list of hosts it may reach. Both are required, so the call
    stops here rather than going out unauthenticated.
    """

    reason = ProxyErrorReason.UNKNOWN_INTEGRATION

    def __init__(self, integration: str, *, known: Sequence[str] = ()) -> None:
        listed = ", ".join(sorted(known)) if known else "none"
        super().__init__(
            f"No injection rule is declared for {integration!r}, so there is no "
            f"sanctioned way for it to authenticate. Declared integrations: {listed}.",
            integration=integration,
        )


class EgressDenied(ProxyError):
    """The request was addressed to a host the integration did not declare (FR-009).

    The rule's own ``hosts`` tuple is the allow-list, so an integration cannot
    reach somewhere it never said it would — which bounds what a prompt-injected
    URL can do even before approval enters the picture.
    """

    reason = ProxyErrorReason.EGRESS_DENIED

    def __init__(self, integration: str, *, host: str, allowed: Sequence[str]) -> None:
        super().__init__(
            f"{integration!r} may not reach {host!r}. Its declared hosts are "
            f"{', '.join(sorted(allowed))}.",
            integration=integration,
            detail=host,
        )
        self.host = host
        self.allowed = tuple(allowed)


class CredentialWouldCrossInClear(ProxyError):
    """A credential resolved, and the destination would carry it unencrypted.

    Same classification as ``EgressDenied`` — ``reason`` is identical, so
    whatever a console derives from the reason does not change — because this
    *is* an egress refusal by every fact the proxy checks. What differs is the
    question the sentence answers. ``EgressDenied``'s message is about the
    allow-list: an address the integration never declared. This refusal has
    nothing wrong with the address; the host is one this integration is
    permitted to reach. What is wrong is the scheme, on a call that is about
    to carry a secret — and telling an operator to check hosts they already
    got right sends them looking at the wrong list.

    Never raised for a request carrying nothing: a self-hosted vendor with no
    authentication of its own is not held to this, because there is nothing
    here to protect. See ``refuse_credential_in_clear``.
    """

    reason = ProxyErrorReason.EGRESS_DENIED

    def __init__(self, integration: str, *, scheme: str, host: str) -> None:
        tls_host = f"https://{host}"
        super().__init__(
            f"{integration!r} would send a stored credential to {scheme}://{host}, and "
            f"{scheme} is never encrypted. Point {integration!r} at {tls_host} instead, "
            f"or remove the stored credential and connect it by address only.",
            integration=integration,
            detail=host,
        )
        self.host = host
        self.scheme = scheme


class CredentialUnavailable(ProxyError):
    """This tenant and team have no credential for this integration.

    Named for what the caller experiences rather than for the storage state,
    because "not configured", "deleted", and "configured for a different team"
    are one situation from where the capability is standing.
    """

    reason = ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED

    def __init__(self, integration: str, *, handle: str, org_id: str, team_id: str) -> None:
        super().__init__(
            f"No credential is configured for {integration!r} for team {team_id!r} "
            f"in organisation {org_id!r}. Add one under the handle {handle!r}.",
            integration=integration,
            detail=handle,
        )
        self.handle = handle


class CredentialFieldsMissing(ProxyError):
    """The stored credential does not carry the fields its injection rule reads.

    A declaration error rather than an operator one: the schema and the rule
    have drifted, most likely by a field rename on one side. It fails here
    rather than sending a request with a header the rule could not fill, which
    a vendor answers with a 401 that looks like a wrong key.
    """

    reason = ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED

    def __init__(self, integration: str, *, handle: str, fields: Sequence[str]) -> None:
        listed = ", ".join(sorted(fields))
        super().__init__(
            f"The stored credential for {integration!r} is missing {listed}, which its "
            f"injection rule needs. The credential schema and the injection rule have "
            f"drifted apart.",
            integration=integration,
            detail=handle,
        )
        self.handle = handle
        self.fields = tuple(fields)


class CredentialUnreadable(ProxyError):
    """A credential is stored but the configured key cannot open it."""

    reason = ProxyErrorReason.CREDENTIAL_UNREADABLE

    def __init__(self, integration: str, *, handle: str) -> None:
        super().__init__(
            f"The credential for {integration!r} is stored but cannot be decrypted with "
            f"the configured encryption key. The key differs from the one that wrote it.",
            integration=integration,
            detail=handle,
        )
        self.handle = handle


class CredentialExpired(ProxyError):
    """A short-lived credential passed its expiry and could not be refreshed."""

    reason = ProxyErrorReason.CREDENTIAL_EXPIRED

    def __init__(self, integration: str, *, handle: str) -> None:
        super().__init__(
            f"The credential for {integration!r} has expired and this integration "
            f"declares no refresh. Rotate it in the vault.",
            integration=integration,
            detail=handle,
        )
        self.handle = handle


class RefreshFailed(ProxyError):
    """The vendor refused to issue a fresh short-lived credential."""

    reason = ProxyErrorReason.REFRESH_FAILED

    def __init__(self, integration: str, *, cause: str) -> None:
        super().__init__(
            f"Refreshing the short-lived credential for {integration!r} failed: {cause}.",
            integration=integration,
            detail=cause,
        )


class TenantRateLimited(ProxyError):
    """This tenant has spent its share of the proxy for the current window (FR-014)."""

    reason = ProxyErrorReason.RATE_LIMITED

    def __init__(
        self,
        integration: str,
        *,
        org_id: str,
        limit: int,
        window_seconds: float,
    ) -> None:
        super().__init__(
            f"Organisation {org_id!r} has made {limit} proxied requests in the last "
            f"{window_seconds:g}s, which is its limit. Requests are refused rather than "
            f"queued, so a runaway loop costs the tenant that started it.",
            integration=integration,
            detail=org_id,
        )
        self.org_id = org_id
        self.limit = limit
        self.window_seconds = window_seconds


class UpstreamUnreachable(ProxyError):
    """The vendor did not answer at all.

    Distinct from a vendor error response, because the two lead to different
    operator actions: one is the vendor's problem and the other is the network
    between here and it.
    """

    reason = ProxyErrorReason.UPSTREAM_UNREACHABLE

    def __init__(self, integration: str, *, host: str, cause: str) -> None:
        super().__init__(
            f"{integration!r} at {host!r} did not answer: {cause}.",
            integration=integration,
            detail=host,
        )
        self.host = host


class CertificateRefused(ProxyError):
    """The address answered, and this deployment would not trust its certificate.

    Three subclasses, one reason, and three sentences, because they lead to
    three different actions: declare trust, compare the new fingerprint against
    what the node shows, or correct the address. Flattening them into one is the
    same mistake in miniature as flattening this whole class into "nothing
    answered" — the operator is told less than the proxy knew.

    Nothing here carries certificate material. A fingerprint is not a secret and
    is exactly what an operator compares against what the host shows them; a PEM
    is bulk that proves nothing more.
    """

    reason = ProxyErrorReason.CERTIFICATE_UNTRUSTED


class CertificateUntrusted(CertificateRefused):
    """Nothing declared what to trust at this address, so nothing was sent."""

    def __init__(self, integration: str, *, host: str, observed: str) -> None:
        super().__init__(
            f"{host} presented a certificate this deployment has no reason to trust, so "
            f"nothing was sent. Its SHA-256 fingerprint is {observed}. Compare that with "
            f"what the host itself shows, then declare trust for this address: pin the "
            f"fingerprint, or supply the authority that issued it.",
            integration=integration,
            detail=host,
        )
        self.host = host
        self.observed = observed


class CertificatePinBroken(CertificateRefused):
    """The address presented a certificate that is not the one pinned for it.

    Refused, and nothing else happens. No fall back to the system trust store,
    no fall back to not verifying, and no adoption of the new fingerprint: a pin
    that updates itself when it does not match is a decorative field, and a
    replaced certificate is the exact event it exists to catch.
    """

    def __init__(
        self,
        integration: str,
        *,
        host: str,
        expected: Sequence[str],
        observed: str,
    ) -> None:
        listed = ", ".join(expected)
        super().__init__(
            f"{host} presented a certificate that is not pinned for it, so nothing was "
            f"sent. Expected {listed}; observed {observed}. Nothing fell back to the "
            f"system trust store and nothing stopped verifying. If the certificate was "
            f"replaced legitimately, declare the new fingerprint deliberately — it is "
            f"not adopted automatically.",
            integration=integration,
            detail=host,
        )
        self.host = host
        self.expected = tuple(expected)
        self.observed = observed


class CertificateNameMismatch(CertificateRefused):
    """The chain validated against the supplied authority and the name did not match.

    Its own sentence because the fix is a different one: the certificate is
    trusted and the address is wrong, which is what happens when a cluster is
    reached by IP and its authority names the nodes. Reported as "not trusted"
    it would send an operator to declare trust they have already declared.
    """

    def __init__(self, integration: str, *, host: str, certificate_names: Sequence[str]) -> None:
        listed = ", ".join(certificate_names) if certificate_names else "no host at all"
        super().__init__(
            f"The certificate {host} presented is trusted — it chains to what was supplied "
            f"for this integration — but it does not name {host}. It names {listed}. Point "
            f"the integration at a name the certificate carries, or pin the node's "
            f"fingerprint instead: a pin replaces the identity check rather than adding "
            f"to it.",
            integration=integration,
            detail=host,
        )
        self.host = host
        self.certificate_names = tuple(certificate_names)


class ReconstructedProxyError(ProxyError):
    """A proxy error rebuilt on the client side of the internal API.

    The specific subclasses above exist so the proxy's own code can raise
    something meaningful; a client that received one over the wire has the
    classification and the message and needs no more than that. Rebuilding the
    exact subclass would mean a registry that has to be edited every time a
    reason is added, and forgetting to edit it would silently downgrade an error
    rather than failing.
    """

    def __init__(
        self,
        message: str,
        *,
        integration: str,
        detail: str = "",
        reason: ProxyErrorReason = ProxyErrorReason.MALFORMED_REQUEST,
    ) -> None:
        super().__init__(message, integration=integration, detail=detail)
        self.reason = reason


def error_from_record(record: Mapping[str, Any]) -> ProxyError:
    """Return the error a wire record describes, carrying its original reason."""
    return ReconstructedProxyError(
        str(record.get("message", "the proxy refused the request")),
        integration=str(record.get("integration", "")),
        detail=str(record.get("detail", "")),
        reason=ProxyErrorReason(str(record.get("reason", ProxyErrorReason.MALFORMED_REQUEST))),
    )


__all__ = [
    "CertificateNameMismatch",
    "CertificatePinBroken",
    "CertificateRefused",
    "CertificateUntrusted",
    "CredentialExpired",
    "CredentialFieldsMissing",
    "CredentialUnavailable",
    "CredentialUnreadable",
    "CredentialWouldCrossInClear",
    "EgressDenied",
    "IntegrationNotDeclared",
    "MalformedProxyRequest",
    "ProxyError",
    "ProxyErrorReason",
    "ReconstructedProxyError",
    "RefreshFailed",
    "TenantRateLimited",
    "UpstreamUnreachable",
    "error_from_record",
]
