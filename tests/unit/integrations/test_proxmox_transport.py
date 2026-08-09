"""Phase 1: how a Proxmox call is authenticated, trusted, and addressed.

Four properties, and each one is a decision that would be tempting to make the
other way.

**The client holds nothing.** Proxmox API tokens are long-lived and, on a
homelab, usually root-equivalent. The credential is declared, the proxy injects
it, and the assertion here is structural rather than behavioural: there is no
constructor parameter and no slot a token could rest in.

**Certificate verification is on.** Homelab Proxmox is self-signed, so the
tempting default is to turn verification off. Supplying the certificate or
pinning its fingerprint is barely harder and does not train an operator to
accept any certificate presented by their own management plane.

**A cluster has several addresses.** A two-node cluster configured with one
node's address becomes unreachable exactly when it matters most, so the client
takes a list and fails over.

**Nothing here reimplements retry or pagination.** Both come from
``integrations/_base``, and the test asserts the absence of a second
implementation rather than the presence of the first.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from integrations._base.client import IntegrationClient
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations.proxmox import schema
from integrations.proxmox.certificates import (
    CertificateTrust,
    UnverifiedTransportRefused,
)
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.endpoints import EndpointRing, NoEndpointReachable

pytestmark = pytest.mark.unit

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "integrations" / "proxmox"

#: A real SHA-256 fingerprint shape: 32 colon-separated hex pairs, as the
#: Proxmox web interface renders the one an operator copies.
FINGERPRINT = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"


# --- The credential -----------------------------------------------------------


def test_the_token_enters_the_request_as_proxmoxs_own_authorization_header() -> None:
    """The header form Proxmox documents, declared rather than coded."""
    header = next(
        injection
        for injection in schema.RULE.injections
        if getattr(injection, "header", "") == "Authorization"
    )

    assert header.template == "PVEAPIToken={value}"
    assert header.fields() == ("api_token",)


def test_the_schema_declares_every_field_the_injection_reads() -> None:
    declared = set(schema.SCHEMA.field_names)

    for injection in schema.RULE.injections:
        assert set(injection.fields()) <= declared


def test_a_privilege_separated_token_and_a_full_one_are_the_same_wire_format() -> None:
    """FR-001. Privilege separation changes what the token may do, not how it is sent."""
    declared = schema.SCHEMA.get("api_token")

    assert declared is not None
    assert declared.pattern is not None
    assert "privilege separation" in declared.description.lower()


def test_the_ticket_path_is_declared_and_refreshable() -> None:
    """FR-002. A deployment that cannot issue tokens still authenticates."""
    rule = schema.ticket_rule_for("proxmox.acme.example")

    assert rule.refreshable
    read = {name for injection in rule.injections for name in injection.fields()}
    assert read == {"ticket", "csrf_token"}
    assert read <= set(schema.SCHEMA.field_names)


def test_the_client_has_no_parameter_or_slot_a_credential_could_rest_in() -> None:
    parameters = set(inspect.signature(ProxmoxClient.__init__).parameters)
    slots = {slot.lstrip("_") for slot in ProxmoxClient.__slots__}

    assert not (parameters | slots) & {"token", "api_token", "password", "secret", "credential"}
    assert issubclass(ProxmoxClient, IntegrationClient)


def test_no_proxmox_module_names_a_credential_field_outside_the_schema() -> None:
    """SC-009, structurally: the only place a field name appears is the declaration."""
    offenders = [
        path.name
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if path.name != "schema.py" and "api_token" in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"these modules name the credential field: {offenders}"


# --- Certificates -------------------------------------------------------------


def test_verification_is_on_by_default() -> None:
    assert CertificateTrust().verifies
    assert CertificateTrust().describe().startswith("verifying")


def test_a_supplied_certificate_is_trusted_and_still_verifies() -> None:
    trust = CertificateTrust.with_certificate("-----BEGIN CERTIFICATE-----\nMIIB\n")

    assert trust.verifies
    assert "supplied certificate" in trust.describe()


def test_a_pinned_fingerprint_is_trusted_and_still_verifies() -> None:
    trust = CertificateTrust.pinned(FINGERPRINT)

    assert trust.verifies
    assert FINGERPRINT[:11] in trust.describe()


def test_a_fingerprint_that_is_not_one_is_refused_rather_than_stored() -> None:
    with pytest.raises(ValueError, match="SHA-256 fingerprint"):
        CertificateTrust.pinned("probably-a-password")


def test_turning_verification_off_requires_an_explicit_audited_setting() -> None:
    with pytest.raises(UnverifiedTransportRefused):
        CertificateTrust(verify=False)


def test_verification_may_be_disabled_when_the_operator_says_why_and_who() -> None:
    trust = CertificateTrust.unverified(
        reason="lab cluster reachable only over a link with no DNS",
        accepted_by="erik@acme.example",
    )

    assert not trust.verifies
    assert "erik@acme.example" in trust.audit_record()["accepted_by"]
    assert trust.audit_record()["reason"]


def test_disabling_verification_without_a_reason_is_refused() -> None:
    with pytest.raises(UnverifiedTransportRefused, match="reason"):
        CertificateTrust.unverified(reason="  ", accepted_by="erik@acme.example")


# --- Endpoints ----------------------------------------------------------------


def test_a_cluster_may_be_configured_with_more_than_one_address() -> None:
    ring = EndpointRing.of("pve01.acme.example", "pve02.acme.example")

    assert ring.hosts == ("pve01.acme.example", "pve02.acme.example")
    assert ring.current == "pve01.acme.example"


def test_a_ring_with_no_endpoint_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one address"):
        EndpointRing.of()


def test_the_ring_advances_past_an_endpoint_that_did_not_answer() -> None:
    ring = EndpointRing.of("a.example", "b.example")

    ring.mark_unreachable("a.example", detail="connection refused")

    assert ring.current == "b.example"
    assert ring.unreachable == ("a.example",)


def test_the_ring_reports_every_address_it_tried_when_none_answered() -> None:
    ring = EndpointRing.of("a.example", "b.example")
    ring.mark_unreachable("a.example", detail="refused")

    with pytest.raises(NoEndpointReachable) as raised:
        ring.mark_unreachable("b.example", detail="timed out")

    assert "a.example" in str(raised.value)
    assert "b.example" in str(raised.value)
    assert "timed out" in str(raised.value)


def test_an_endpoint_that_comes_back_is_usable_again() -> None:
    """A node that was rebooting is not a node that is gone."""
    ring = EndpointRing.of("a.example", "b.example")
    ring.mark_unreachable("a.example", detail="rebooting")

    ring.mark_reachable("a.example")

    assert ring.unreachable == ()
    assert ring.current == "a.example"


async def test_the_cluster_stays_reachable_through_a_surviving_node() -> None:
    """SC-007. The configured node is the one that is down."""
    attempted: list[str] = []

    async def send(host: str) -> str:
        attempted.append(host)
        if host == "pve01.acme.example":
            raise IntegrationError(
                "connection refused",
                integration="proxmox",
                reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
            )
        return "answered"

    ring = EndpointRing.of("pve01.acme.example", "pve02.acme.example")

    assert await ring.attempt(send) == "answered"
    assert attempted == ["pve01.acme.example", "pve02.acme.example"]
    assert ring.current == "pve02.acme.example"


async def test_a_failure_that_is_not_about_reachability_is_not_failed_over() -> None:
    """A 403 from one node is a 403 from all of them, and retrying hides it."""
    attempted: list[str] = []

    async def send(host: str) -> str:
        attempted.append(host)
        raise IntegrationError(
            "insufficient privileges",
            integration="proxmox",
            reason=IntegrationErrorReason.FORBIDDEN,
        )

    ring = EndpointRing.of("pve01.acme.example", "pve02.acme.example")

    with pytest.raises(IntegrationError):
        await ring.attempt(send)
    assert attempted == ["pve01.acme.example"]


# --- Retry and pagination come from the base ----------------------------------


def test_the_package_reimplements_neither_retry_nor_pagination() -> None:
    """T-006. The check is the absence of a second implementation.

    Waiting between polls of a long-running task is not retry and is not banned:
    it is what "report a task still running rather than waiting indefinitely"
    is made of. What is banned is a second backoff schedule, a second retryable
    set, or a second pagination walk — each of which would make this vendor
    behave differently from the other eighty-odd under load.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        body = path.read_text(encoding="utf-8")
        for banned in ("class RetryPolicy", "def walk(", "def parse_retry_after", "backoff"):
            if banned in body:
                offenders.append(f"{path.name}: {banned}")

    assert not offenders, "\n".join(offenders)


def test_the_client_takes_its_retry_policy_from_the_shared_base() -> None:
    import inspect

    from integrations._base.retry import RetryPolicy

    signature = inspect.signature(ProxmoxClient.__init__)

    assert signature.parameters["retry"].annotation == "RetryPolicy | None"
    assert RetryPolicy is not None


def test_the_client_declares_its_pagination_through_the_shared_vocabulary() -> None:
    from integrations._base.pagination import EndpointPagination
    from integrations.proxmox.client import PAGINATION

    assert PAGINATION
    assert all(isinstance(declared, EndpointPagination) for declared in PAGINATION)


def test_the_tested_proxmox_versions_are_stated_in_exactly_one_place() -> None:
    """NFR-005. One tuple, and every other mention reads it."""
    assert schema.TESTED_VERSIONS
    mentions = [
        path.name
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if path.name != "schema.py" and "TESTED_VERSIONS = " in path.read_text(encoding="utf-8")
    ]

    assert not mentions
