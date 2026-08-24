"""What the proxy's egress actually accepts, against a real TLS handshake.

Nothing here is mocked below the socket. A certificate authority and two leaf
certificates are minted in the fixture, an HTTPS server is stood up on the
loopback with one of them, and the sender is pointed at it — so "the pin works"
is measured by a handshake rather than asserted about a branch.

Nothing is committed either: every key exists for the lifetime of one test
process, in a temporary directory, and no private key material reaches the
repository.
"""

from __future__ import annotations

import datetime as dt
import http.server
import ipaddress
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from platform.credentials.proxy.errors import (
    CertificateNameMismatch,
    CertificatePinBroken,
    CertificateUntrusted,
    ProxyErrorReason,
    UpstreamUnreachable,
)
from platform.credentials.proxy.model import OutboundRequest
from platform.credentials.proxy.trust import CertificateTrust, TrustRegistry

pytestmark = pytest.mark.contract

LOOPBACK = "127.0.0.1"
#: A name the certificates carry and the loopback address does not answer to,
#: which is exactly the shape of a cluster reached by IP.
NODE_NAME = "pve01.acme.example"


# -- a certificate authority and the leaves it issues ---------------------------


def _authority() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Return a self-signed authority, the way an appliance mints its own."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "acme cluster authority")])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        # Deliberately without ``keyUsage``. An appliance that mints its own
        # authority predictably omits it, and that omission is what the
        # conformance relaxation below exists to tolerate — reproducing it here
        # is what makes the relaxation measured rather than assumed.
        .sign(key, hashes.SHA256())
    )
    return certificate, key


def _leaf(
    authority: x509.Certificate,
    authority_key: ec.EllipticCurvePrivateKey,
    *,
    names: tuple[str, ...],
    addresses: tuple[str, ...] = (),
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Return a certificate the authority issued for ``names``."""
    key = ec.generate_private_key(ec.SECP256R1())
    alternatives: list[x509.GeneralName] = [x509.DNSName(name) for name in names]
    alternatives.extend(x509.IPAddress(ipaddress.ip_address(one)) for one in addresses)
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(authority.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(alternatives), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    return certificate, key


def _write(
    directory: Path,
    stem: str,
    certificate: x509.Certificate,
    key: ec.EllipticCurvePrivateKey,
) -> tuple[Path, str]:
    """Write ``certificate`` and ``key`` where a server can load them."""
    pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
    combined = directory / f"{stem}.pem"
    combined.write_text(
        pem
        + key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii"),
        encoding="ascii",
    )
    return combined, pem


def _fingerprint(certificate: x509.Certificate) -> str:
    """Return the SHA-256 fingerprint as a management interface shows it."""
    digest = certificate.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


# -- the server the sender talks to ---------------------------------------------


class _Answer(http.server.BaseHTTPRequestHandler):
    """Answers every GET with a fixed body, and says nothing to the log."""

    def do_GET(self) -> None:  # noqa: N802 — the base class names it
        body = b'{"data":{"version":"8.2.4"}}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        """Keep the test output readable."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One TLS server, and the material a client would be given about it."""

    url: str
    host: str
    fingerprint: str
    authority_pem: str


def _serve(certificate_path: Path) -> Iterator[tuple[str, int]]:
    """Run one HTTPS server on the loopback for the life of a test."""
    server = http.server.ThreadingHTTPServer((LOOPBACK, 0), _Answer)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[0], server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@dataclass(frozen=True, slots=True)
class Cluster:
    """An authority, and two nodes it issued certificates to."""

    authority_pem: str
    first: Endpoint
    second: Endpoint


@pytest.fixture
def named_node(tmp_path: Path) -> Iterator[Endpoint]:
    """Return a server whose certificate names the address it answers on."""
    authority, authority_key = _authority()
    certificate, key = _leaf(authority, authority_key, names=(NODE_NAME,), addresses=(LOOPBACK,))
    path, _ = _write(tmp_path, "node", certificate, key)
    for host, port in _serve(path):
        yield Endpoint(
            url=f"https://{host}:{port}/api2/json/version",
            host=host,
            fingerprint=_fingerprint(certificate),
            authority_pem=authority.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        )


@pytest.fixture
def misnamed_node(tmp_path: Path) -> Iterator[Endpoint]:
    """Return a server whose certificate names a node, not the address used."""
    authority, authority_key = _authority()
    certificate, key = _leaf(authority, authority_key, names=(NODE_NAME,))
    path, _ = _write(tmp_path, "node", certificate, key)
    for host, port in _serve(path):
        yield Endpoint(
            url=f"https://{host}:{port}/api2/json/version",
            host=host,
            fingerprint=_fingerprint(certificate),
            authority_pem=authority.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        )


def _request(endpoint: Endpoint) -> OutboundRequest:
    """Return the request a proxy would put on the wire."""
    return OutboundRequest(method="GET", url=endpoint.url, headers={"accept": "application/json"})


def _sender(*declarations: CertificateTrust):
    """Return a sender carrying the trust registry composition would give it."""
    from gateway.proxy.sender import HttpOutboundSender

    return HttpOutboundSender(trust=TrustRegistry(declarations))


# -- the three modes -------------------------------------------------------------


async def test_an_undeclared_address_is_refused_for_its_certificate_not_its_network(
    named_node: Endpoint,
) -> None:
    with pytest.raises(CertificateUntrusted) as refused:
        await _sender().send(_request(named_node), timeout_seconds=5)

    assert refused.value.reason is ProxyErrorReason.CERTIFICATE_UNTRUSTED
    assert "did not answer" not in str(refused.value)


async def test_the_refusal_names_the_fingerprint_the_address_actually_presented(
    named_node: Endpoint,
) -> None:
    with pytest.raises(CertificateUntrusted) as refused:
        await _sender().send(_request(named_node), timeout_seconds=5)

    assert named_node.fingerprint in str(refused.value)
    assert refused.value.observed == named_node.fingerprint


async def test_the_correct_fingerprint_pinned_reaches_the_endpoint(
    named_node: Endpoint,
) -> None:
    declared = CertificateTrust.pinned(named_node.fingerprint).for_addresses(named_node.host)

    answer = await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert answer.status_code == 200
    assert b"8.2.4" in answer.body


async def test_a_fingerprint_pinned_without_separators_reaches_the_endpoint(
    named_node: Endpoint,
) -> None:
    bare = named_node.fingerprint.replace(":", "")
    declared = CertificateTrust.pinned(bare).for_addresses(named_node.host)

    answer = await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert answer.status_code == 200


async def test_the_supplied_authority_reaches_the_endpoint(named_node: Endpoint) -> None:
    declared = CertificateTrust.with_certificate(named_node.authority_pem).for_addresses(
        named_node.host
    )

    answer = await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert answer.status_code == 200
    assert b"8.2.4" in answer.body


async def test_an_accepted_unverified_certificate_reaches_the_endpoint(
    named_node: Endpoint,
) -> None:
    declared = CertificateTrust.unverified(
        reason="lab cluster on a link with no DNS", accepted_by="erik@acme.example"
    ).for_addresses(named_node.host)

    answer = await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert answer.status_code == 200


# -- the pin holds ----------------------------------------------------------------


def _wrong_pin(endpoint: Endpoint) -> str:
    """Return a well-formed fingerprint that is not the one presented."""
    return "FF:" + endpoint.fingerprint[3:]


async def test_a_pin_that_does_not_match_refuses_and_names_both_fingerprints(
    named_node: Endpoint,
) -> None:
    expected = _wrong_pin(named_node)
    declared = CertificateTrust.pinned(expected).for_addresses(named_node.host)

    with pytest.raises(CertificatePinBroken) as refused:
        await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert expected in str(refused.value)
    assert named_node.fingerprint in str(refused.value)
    assert "did not answer" not in str(refused.value)


async def test_a_broken_pin_refuses_again_rather_than_degrading(
    named_node: Endpoint,
) -> None:
    declared = CertificateTrust.pinned(_wrong_pin(named_node)).for_addresses(named_node.host)
    sender = _sender(declared)

    for _ in range(3):
        with pytest.raises(CertificatePinBroken):
            await sender.send(_request(named_node), timeout_seconds=5)


async def test_a_broken_pin_leaves_the_declaration_exactly_as_it_was_written(
    named_node: Endpoint,
) -> None:
    expected = _wrong_pin(named_node)
    declared = CertificateTrust.pinned(expected).for_addresses(named_node.host)
    registry = TrustRegistry([declared])
    from gateway.proxy.sender import HttpOutboundSender

    sender = HttpOutboundSender(trust=registry)
    with pytest.raises(CertificatePinBroken):
        await sender.send(_request(named_node), timeout_seconds=5)

    assert registry.for_host(named_node.host).fingerprints == (expected,)


async def test_one_node_changing_its_certificate_leaves_the_others_reachable(
    named_node: Endpoint,
    misnamed_node: Endpoint,
) -> None:
    """A cluster declares one fingerprint per node in a single declaration.

    Both servers answer on the loopback, so the two are distinguished by port —
    which is what a declaration scoped by host cannot separate. So the cluster
    is expressed as one declaration carrying both fingerprints, one of them
    stale: the surviving node's fingerprint is still in the set, and the call
    still goes through.
    """
    declared = CertificateTrust.pinned(
        _wrong_pin(misnamed_node), named_node.fingerprint
    ).for_addresses(named_node.host)

    answer = await _sender(declared).send(_request(named_node), timeout_seconds=5)

    assert answer.status_code == 200


# -- the name that does not match --------------------------------------------------


async def test_a_trusted_chain_with_the_wrong_name_is_its_own_refusal(
    misnamed_node: Endpoint,
) -> None:
    declared = CertificateTrust.with_certificate(misnamed_node.authority_pem).for_addresses(
        misnamed_node.host
    )

    with pytest.raises(CertificateNameMismatch) as refused:
        await _sender(declared).send(_request(misnamed_node), timeout_seconds=5)

    assert misnamed_node.host in str(refused.value)
    assert NODE_NAME in str(refused.value)
    assert "did not answer" not in str(refused.value)


async def test_a_pin_has_no_name_problem_at_the_same_address(
    misnamed_node: Endpoint,
) -> None:
    """The reason the setup document says to try the fingerprint first."""
    declared = CertificateTrust.pinned(misnamed_node.fingerprint).for_addresses(misnamed_node.host)

    answer = await _sender(declared).send(_request(misnamed_node), timeout_seconds=5)

    assert answer.status_code == 200


# -- and the default did not loosen -------------------------------------------------


def test_the_default_context_stays_as_strict_as_the_library_is() -> None:
    from gateway.proxy.sender import trust_context

    context = trust_context({})

    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.verify_flags & ssl.VERIFY_X509_STRICT


def test_a_supplied_certificate_relaxes_conformance_and_nothing_more(
    named_node: Endpoint,
) -> None:
    """The relaxation follows the operator's own anchor, and only that.

    An appliance mints its authority without the key-usage extension the
    standard asks for, so refusing it would make the whole supplied-certificate
    form useless for the case it exists to serve. Chain, expiry and name
    checking all stay on, which is what the previous test measures against the
    default and this one measures here.
    """
    from gateway.proxy.sender import context_for_trust

    declared = CertificateTrust.with_certificate(named_node.authority_pem)
    context = context_for_trust(declared)

    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT


def test_only_a_declaration_reaches_a_context_that_does_not_verify() -> None:
    from gateway.proxy.sender import context_for_trust

    unverified = context_for_trust(
        CertificateTrust.unverified(reason="lab", accepted_by="erik@acme")
    )
    default = context_for_trust(CertificateTrust())

    assert unverified.verify_mode is ssl.CERT_NONE
    assert default.verify_mode is ssl.CERT_REQUIRED


# -- and a silent address still says what it says today ------------------------------


async def test_an_address_that_does_not_answer_is_still_unreachable_not_untrusted() -> None:
    from gateway.proxy.sender import HttpOutboundSender

    # Port 1 on the loopback: nothing binds it, so the connection is refused
    # before any certificate exists to have an opinion about.
    request = OutboundRequest(method="GET", url=f"https://{LOOPBACK}:1/api2/json/version")

    with pytest.raises(UpstreamUnreachable) as refused:
        await HttpOutboundSender().send(request, timeout_seconds=5)

    assert "certificate" not in str(refused.value).lower()
    assert refused.value.reason is ProxyErrorReason.UPSTREAM_UNREACHABLE
