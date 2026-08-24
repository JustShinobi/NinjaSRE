"""What actually puts the proxy's bytes on the wire, and what it trusts while doing it.

The standard library rather than an HTTP client library, for one reason that is
specific to this component: the credential proxy is the process that holds the
secrets, and the smallest dependency tree in the deployment belongs here. An
async client would be faster under load; nothing here is on an investigation's
critical path more than once per tool call, and "what is in this container" is a
question a security review asks about this container in particular.

``urllib`` is synchronous, so each send runs in a worker thread. That is a
thread per in-flight outbound call, bounded by the deployment's own concurrency
ceiling — which is a profile-scoped named constant, so the bound exists.

**Trust is decided per address, and this is the only place it is applied.** An
appliance that mints its own certificate is the ordinary self-hosted case, and
the decision about what to accept from it belongs to the operator. It travels
here as a declaration — a trust registry handed to this sender by composition,
and reachable no other way — and it is turned into one TLS context per address,
built once and reused rather than per request.

**This is the only module in the tree that can build a context that does not
verify.** ``context_for_trust`` is that place, it is reachable only from a
declaration that recorded a reason and who accepted it, and an architecture test
fails naming any second one. A pin uses it too, and for a reason worth stating:
a pinned fingerprint *replaces* identity verification rather than adding to it,
which is what makes pinning the form that works for a cluster reached by IP
address. The certificate is then checked against the declared set immediately
after the handshake and before a single byte is sent.

**The trust store is the other half.** An operator behind a proxy that
terminates TLS has a certificate authority the system store does not know, and
the failure mode without it is every outbound call failing verification at once.
``NINJASRE_CA_BUNDLE`` names a bundle to trust *in addition to* the system's.
There is deliberately no setting that turns verification off: a deployment that
skipped it would send credentials to whoever answered.

**Naming a bundle also drops RFC 5280 strictness, and only that.** Python 3.13
turned ``VERIFY_X509_STRICT`` on by default, which requires a certificate
authority to carry ``keyUsage=keyCertSign,cRLSign``. An appliance that mints
its own authority predictably omits it — Proxmox VE does — so a deployment
pointed at its own cluster fails every call with "CA cert does not include key
usage extension" no matter how correctly the bundle was configured. Chain
building, expiry and hostname checking all stay on; what is relaxed is one
conformance rule about how the operator's own authority was minted, and the
operator naming the anchor is the decision that relaxes it. A certificate
supplied through configuration is the same decision by a different route and
gets the same relaxation, and nothing else does.

**A refused certificate is not an unreachable address.** Those two were caught
on one line here, and the sentence an operator got sent them to check a network
that was fine. They are separated below, and naming the certificate in the
refusal costs a second handshake — see ``_observed_fingerprint``.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import os
import socket
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from config.constants.deployment import NINJASRE_CA_BUNDLE_ENV
from config.constants.security import CREDENTIAL_PROXY_TIMEOUT_SECONDS
from platform.credentials.proxy.errors import (
    CertificateNameMismatch,
    CertificatePinBroken,
    CertificateUntrusted,
    UpstreamUnreachable,
)
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.trust import (
    CertificateTrust,
    TrustAnchor,
    TrustRegistry,
)

#: The two OpenSSL verification results that mean "the chain is fine and the
#: name is not". Codes rather than the message, because the message is prose
#: that changes between library versions and these are part of its ABI:
#: ``X509_V_ERR_HOSTNAME_MISMATCH`` and ``X509_V_ERR_IP_ADDRESS_MISMATCH``.
_NAME_MISMATCH_CODES: frozenset[int] = frozenset({62, 64})

#: What a TLS endpoint answers on when the address names no port.
_DEFAULT_TLS_PORT = 443

#: How long a diagnostic handshake — the one that exists only to name the
#: certificate in a refusal — may take. Short: the call has already failed and
#: nobody is waiting on the explanation longer than they waited on the answer.
_DIAGNOSTIC_TIMEOUT_SECONDS = 5.0


def trust_context(environ: Mapping[str, str] | None = None) -> ssl.SSLContext:
    """Return the TLS context outbound calls verify against by default.

    The system store, plus the operator's bundle when they named one. Raises
    rather than falling back to the system store alone if the bundle cannot be
    loaded: a deployment that silently ignored its configured trust anchor
    would fail every call to the vendor behind the intercepting proxy, and the
    reason would be nowhere.

    A deployment that named no bundle stays as strict as the standard library
    is, so nothing about verifying a public vendor changes here.
    """
    source = environ if environ is not None else os.environ
    context = ssl.create_default_context()
    bundle = source.get(NINJASRE_CA_BUNDLE_ENV, "").strip()
    if bundle:
        context.load_verify_locations(cafile=str(Path(bundle)))
        # See the module docstring: an appliance's own authority is minted
        # without the extension RFC 5280 wants, and refusing it would make the
        # bundle setting useless for the case it exists to serve.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def context_for_trust(
    trust: CertificateTrust, *, default: ssl.SSLContext | None = None
) -> ssl.SSLContext:
    """Return the TLS context ``trust`` describes.

    The one function in the repository that can produce a context which does not
    verify, and it does so only for a declaration that already carries a reason
    and the identity of whoever accepted it — the value refuses to exist
    otherwise. A second such function anywhere is a second thing a security
    review has to find, so an architecture test fails naming it.
    """
    match trust.anchor:
        case TrustAnchor.SYSTEM_TRUST_STORE:
            return default if default is not None else trust_context()
        case TrustAnchor.SUPPLIED_CERTIFICATE:
            context = ssl.create_default_context(cadata=trust.certificate_pem)
            # The same relaxation a named bundle gets, for the same reason and
            # for nothing else: an appliance's own authority omits the key-usage
            # extension the standard asks for. Chain, expiry and name checking
            # all stay on — see the two assertions in the egress contract suite.
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
            return context
        case TrustAnchor.PINNED_FINGERPRINT | TrustAnchor.UNVERIFIED:
            # A pin replaces the identity check rather than adding to it, which
            # is exactly why it is the form that works for a cluster reached by
            # IP address. The certificate is compared against the declared set
            # in `_PinCheckingConnection.connect`, before anything is sent — so
            # this context alone is never what decides a pinned call.
            unverified = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            unverified.check_hostname = False
            unverified.verify_mode = ssl.CERT_NONE
            return unverified


class _PinRefused(Exception):  # noqa: N818 — signalling, caught two frames up
    """The address presented a certificate outside the pinned set.

    Deliberately not an ``OSError``: ``urllib`` wraps those into ``URLError``,
    and this has to arrive at the caller carrying the two fingerprints rather
    than as one more thing that could not be reached.
    """

    def __init__(self, *, observed: str, expected: Sequence[str]) -> None:
        super().__init__("the certificate presented is not the one pinned")
        self.observed = observed
        self.expected = tuple(expected)


class _PinCheckingConnection(http.client.HTTPSConnection):
    """An HTTPS connection that refuses before the request is written.

    The check has to happen here rather than around the response, because a
    check that ran afterwards would have sent the credential to whatever
    answered. ``connect`` is the last moment before ``request`` writes bytes.
    """

    pin: CertificateTrust | None = None

    def connect(self) -> None:
        """Open the connection, then refuse it unless the pin matches."""
        super().connect()
        declared = self.pin
        if declared is None:
            return
        presented = getattr(self.sock, "getpeercert", None)
        observed = fingerprint_of(presented(binary_form=True) if presented else None)
        if not declared.matches_fingerprint(observed):
            self.close()
            raise _PinRefused(observed=observed, expected=declared.fingerprints)


class _PinCheckingHandler(urllib.request.HTTPSHandler):
    """Opens HTTPS through a connection class that checks the pin."""

    def __init__(
        self,
        *,
        context: ssl.SSLContext,
        connection: Callable[..., http.client.HTTPSConnection],
    ) -> None:
        super().__init__(context=context)
        self._connection = connection
        self._ssl_context = context

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        """Open ``req`` with the pin-checking connection rather than the default."""
        opened = self.do_open(self._connection, req, context=self._ssl_context)
        return opened


def fingerprint_of(certificate: bytes | None) -> str:
    """Return a DER certificate's SHA-256 fingerprint, spelled as a node shows it.

    Colon-separated uppercase hex, because the value exists to be compared by a
    person against what the management interface prints. A fingerprint is not a
    secret: it is the public half's digest, and it is what an operator needs in
    the refusal.
    """
    if not certificate:
        return ""
    digest = hashlib.sha256(certificate).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


@dataclass(frozen=True, slots=True)
class _Egress:
    """One address's resolved decision: what is trusted, and how to open with it."""

    trust: CertificateTrust
    context: ssl.SSLContext
    opener: urllib.request.OpenerDirector


class HttpOutboundSender:
    """Sends one already-authenticated request and returns what came back.

    Never retries. Retry policy belongs to the integration client, which knows
    whether the operation is idempotent; a proxy that retried on its own would
    turn one write into two for every vendor whose timeout is optimistic.
    """

    __slots__ = ("_default", "_egress", "_generation", "_trust")

    def __init__(
        self,
        *,
        context: ssl.SSLContext | None = None,
        trust: TrustRegistry | None = None,
    ) -> None:
        self._default = context if context is not None else trust_context()
        #: Handed in by composition and obtainable no other way. A sender that
        #: could build its own would be a second place trust is decided.
        self._trust = trust if trust is not None else TrustRegistry()
        self._egress: dict[str, _Egress] = {}
        self._generation = self._trust.generation

    async def send(
        self,
        request: OutboundRequest,
        *,
        timeout_seconds: float = CREDENTIAL_PROXY_TIMEOUT_SECONDS,
    ) -> OutboundResponse:
        """Send ``request`` and return the vendor's answer.

        Raises ``UpstreamUnreachable`` when nothing came back at all, and a
        ``CertificateRefused`` when something answered and this deployment would
        not trust it. A status the vendor sent and a failure the proxy invented
        lead to different operator actions, so an invented 502 is never returned.
        """
        return await asyncio.to_thread(self._send, request, timeout_seconds)

    # -- the decision per address ---------------------------------------------

    def _egress_for(self, host: str) -> _Egress:
        """Return the resolved egress for ``host``, building it at most once.

        Once per address rather than once per request: a context is the
        expensive object here, and rebuilding one per call is handshake cost the
        feature has no reason to pay. The cache is dropped whole when the
        registry is rebuilt, which is what makes a declaration an operator
        removed stop applying on the next cycle rather than at the next restart.
        """
        if self._generation != self._trust.generation:
            self._egress.clear()
            self._generation = self._trust.generation
        found = self._egress.get(host)
        if found is not None:
            return found
        declared = self._trust.for_host(host)
        context = context_for_trust(declared, default=self._default)
        built = _Egress(trust=declared, context=context, opener=_opener(declared, context))
        self._egress[host] = built
        return built

    # -- one send --------------------------------------------------------------

    def _send(self, request: OutboundRequest, timeout_seconds: float) -> OutboundResponse:
        split = urlsplit(request.url)
        host = request.host or split.hostname or request.url
        egress = self._egress_for(host)
        prepared = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method.upper(),
        )
        try:
            with egress.opener.open(  # noqa: S310 — the URL is allow-listed upstream
                prepared, timeout=timeout_seconds
            ) as answer:
                return OutboundResponse(
                    status_code=int(answer.status),
                    headers={key.lower(): value for key, value in answer.headers.items()},
                    body=answer.read(),
                )
        except urllib.error.HTTPError as answer:
            # A status the vendor actually sent. Not an error from the proxy's
            # point of view: a 401 is the answer to "is this credential valid",
            # and swallowing it would lose the one thing the caller needed.
            return OutboundResponse(
                status_code=int(answer.code),
                headers={key.lower(): value for key, value in answer.headers.items()},
                body=answer.read(),
            )
        except _PinRefused as broken:
            # No integration name: this layer is handed a request, not the rule
            # that authenticated it. The engine names it on the way out, which
            # is where that fact lives.
            raise CertificatePinBroken(
                "", host=host, expected=broken.expected, observed=broken.observed
            ) from broken
        except (urllib.error.URLError, ssl.SSLError, OSError) as error:
            refused = _certificate_failure(error)
            if refused is not None:
                raise self._refusal(refused, host=host, port=split.port, egress=egress) from error
            raise UpstreamUnreachable(
                "",
                host=host,
                cause=f"{type(error).__name__}: {error}",
            ) from error

    def _refusal(
        self,
        failure: ssl.SSLCertVerificationError,
        *,
        host: str,
        port: int | None,
        egress: _Egress,
    ) -> CertificateUntrusted | CertificateNameMismatch:
        """Return the refusal that names what actually went wrong, and with what.

        Both branches cost one more handshake, and both of those handshakes send
        nothing at all. The standard library gives no access to a certificate
        whose verification failed, so the alternative to a second handshake is a
        message that says "not trusted" and names nothing — which is the shape of
        message this whole feature exists to remove.
        """
        at = port or _DEFAULT_TLS_PORT
        if failure.verify_code in _NAME_MISMATCH_CODES:
            # The chain is sound, so the diagnostic handshake keeps verifying it
            # and only turns off the check that failed. Nothing unverified is
            # constructed to produce this message.
            return CertificateNameMismatch(
                "", host=host, certificate_names=_certificate_names(host, at, egress.context)
            )
        return CertificateUntrusted("", host=host, observed=_observed_fingerprint(host, at))


def _opener(trust: CertificateTrust, context: ssl.SSLContext) -> urllib.request.OpenerDirector:
    """Return the opener that applies ``trust`` for one address."""
    if trust.anchor is not TrustAnchor.PINNED_FINGERPRINT:
        return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def connection(host: str, **arguments: object) -> http.client.HTTPSConnection:
        built = _PinCheckingConnection(host, **arguments)  # type: ignore[arg-type]
        built.pin = trust
        return built

    return urllib.request.build_opener(_PinCheckingHandler(context=context, connection=connection))


def _certificate_failure(error: BaseException) -> ssl.SSLCertVerificationError | None:
    """Return the verification failure inside ``error``, or ``None``.

    ``urllib`` wraps anything an ``OSError`` subclass raised during ``connect``
    into a ``URLError``, so the fact that this was a certificate rather than a
    cable arrives one level down.
    """
    if isinstance(error, ssl.SSLCertVerificationError):
        return error
    inner = getattr(error, "reason", None)
    if isinstance(inner, ssl.SSLCertVerificationError):
        return inner
    return None


def _observed_fingerprint(host: str, port: int) -> str:
    """Return the fingerprint ``host`` presents, for a refusal that names it.

    Opens a bare TLS connection and closes it: the handshake completes, the
    certificate is read, and **not one byte of the request is written**. The
    call it explains has already been refused, and nothing about this connection
    can carry a credential — there is no request on it to inject one into.
    """
    try:
        with socket.create_connection((host, port), timeout=_DIAGNOSTIC_TIMEOUT_SECONDS) as raw:
            unverified = context_for_trust(
                CertificateTrust.unverified(
                    reason="reading the certificate that was already refused, sending nothing",
                    accepted_by="the proxy, to name it in the refusal",
                )
            )
            with unverified.wrap_socket(raw, server_hostname=host) as tls:
                return fingerprint_of(tls.getpeercert(binary_form=True))
    except OSError:
        # The address answered a moment ago and does not now. Saying nothing
        # about the fingerprint is honest; inventing one is not.
        return ""


def _certificate_names(host: str, port: int, context: ssl.SSLContext) -> tuple[str, ...]:
    """Return the names the certificate at ``host`` carries.

    Verifies the chain exactly as the refused call did and turns off only the
    name check, which is the check that failed. Sends nothing.
    """
    try:
        naming = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        naming.check_hostname = False
        naming.verify_mode = ssl.CERT_REQUIRED
        naming.verify_flags = context.verify_flags
        naming.load_verify_locations(cadata=_anchors_of(context))
        with (
            socket.create_connection((host, port), timeout=_DIAGNOSTIC_TIMEOUT_SECONDS) as raw,
            naming.wrap_socket(raw, server_hostname=host) as tls,
        ):
            return _names_in(tls.getpeercert() or {})
    except (OSError, ValueError):
        return ()


def _anchors_of(context: ssl.SSLContext) -> str:
    """Return the trust anchors ``context`` holds, as PEM for a second context.

    Read back off the context rather than from the declaration, so the
    diagnostic connection trusts exactly what the refused one did — including a
    system store this deployment never named.
    """
    return "\n".join(
        ssl.DER_cert_to_PEM_cert(anchor) for anchor in context.get_ca_certs(binary_form=True)
    )


def _names_in(certificate: Mapping[str, object]) -> tuple[str, ...]:
    """Return every host name and address a parsed certificate names."""
    found: list[str] = []
    alternatives = certificate.get("subjectAltName", ())
    if isinstance(alternatives, tuple):
        found.extend(
            str(value)
            for kind, value in alternatives
            if kind in {"DNS", "IP Address"} and str(value)
        )
    subject = certificate.get("subject", ())
    if isinstance(subject, tuple):
        for part in subject:
            for key, value in part:
                if key == "commonName" and str(value) not in found:
                    found.append(str(value))
    return tuple(found)


__all__ = [
    "HttpOutboundSender",
    "context_for_trust",
    "fingerprint_of",
    "trust_context",
]
