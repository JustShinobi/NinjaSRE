"""Writing down what this deployment accepts from an endpoint's certificate.

Four properties, each with a way it would be silently wrong.

**The identity on the record is the authenticated one.** A name the client put
in the body is what makes an audit trail a place people write whatever they
like.

**Nothing is written without the permission.** Not partially, not the address,
not the fingerprints — the refusal has to leave the document as it was.

**The declaration survives the next address write.** The function that rewrites
the entry list copies a fixed set of fields, and a field outside that set is
erased by the first save afterwards. That defect has already happened in this
code base once.

**No certificate material reaches the audit trail.** A fingerprint may: it is
the public half's digest and it is what an operator compares.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway.http.integration_endpoints import (
    configured_trust,
    record_certificate_trust,
    stamped_trust,
    trust_audit_detail,
)
from platform.credentials.proxy.trust import TrustAnchor
from platform.identity.errors import PermissionDenied
from platform.identity.permissions import Permission
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

pytestmark = pytest.mark.unit

COLONS = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"
PEM = "-----BEGIN CERTIFICATE-----\nMIIBogIBADANBgkq\n-----END CERTIFICATE-----\n"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIBogIBADANBgkq\n-----END PRIVATE KEY-----\n"
AT = datetime(2026, 8, 24, 9, 30, tzinfo=UTC)
WHO = "user-admin"
#: This test seeds its own organisation rather than importing the package
#: fixture's name. Two `conftest` modules with the same basename collide when
#: pytest is pointed at more than one tree at once, and a test that only passes
#: when it is run alone is a test nobody trusts.
ORG = "acme"


async def _store() -> FakePersistence:
    """Return a store with one organisation, ready to hold a configuration tree."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return gateway


class _Holding:
    """A permission set holding exactly what it was given."""

    def __init__(self, *held: Permission) -> None:
        self._held = frozenset(held)

    def require(self, permission: Permission, *, node_id: str | None = None) -> None:
        del node_id
        if permission not in self._held:
            raise PermissionDenied(permission, node_id=None, principal_id=WHO)


# -- what the server stamps, and what it ignores ---------------------------------


def test_the_identity_written_down_is_the_authenticated_one() -> None:
    stamped = stamped_trust(
        {"unverified_reason": "lab link with no DNS", "unverified_accepted_by": "somebody-else"},
        actor_id=WHO,
        at=AT,
    )

    assert stamped.unverified_accepted_by == WHO


def test_the_instant_written_down_is_the_server_s() -> None:
    stamped = stamped_trust(
        {"unverified_reason": "lab link with no DNS", "unverified_accepted_at": "1999-01-01"},
        actor_id=WHO,
        at=AT,
    )

    assert stamped.unverified_accepted_at == AT.isoformat()


def test_a_declaration_that_is_not_unverified_carries_no_identity_at_all() -> None:
    stamped = stamped_trust({"fingerprints": [COLONS]}, actor_id=WHO, at=AT)

    assert stamped.anchor_is(TrustAnchor.PINNED_FINGERPRINT)
    assert not stamped.unverified_accepted_by
    assert not stamped.unverified_accepted_at


def test_accepting_unverified_with_a_blank_reason_is_refused_naming_the_reason() -> None:
    """The server supplies the identity, so a blank reason is the only thing missing."""
    with pytest.raises(ValueError, match="reason"):
        stamped_trust({"unverified_reason": "   "}, actor_id=WHO, at=AT)


def test_a_private_key_is_refused_before_anything_is_written() -> None:
    with pytest.raises(ValueError, match="private key"):
        stamped_trust({"certificate_pem": PRIVATE_KEY}, actor_id=WHO, at=AT)


# -- who may write which form -----------------------------------------------------


@pytest.mark.parametrize("declared", [{"fingerprints": [COLONS]}, {"certificate_pem": PEM}])
def test_pinning_and_supplying_need_only_the_permission_that_writes_an_address(
    declared: dict[str, object],
) -> None:
    """They narrow the anchor rather than widening it, so they are not privileged."""
    stamped = stamped_trust(declared, actor_id=WHO, at=AT)

    stamped.refuse_unless_permitted(_Holding(Permission.INTEGRATION_MANAGE))


def test_accepting_unverified_without_the_dedicated_permission_is_refused() -> None:
    stamped = stamped_trust({"unverified_reason": "lab link"}, actor_id=WHO, at=AT)

    with pytest.raises(PermissionDenied) as refused:
        stamped.refuse_unless_permitted(_Holding(Permission.INTEGRATION_MANAGE))

    assert Permission.INTEGRATION_TRUST_UNVERIFIED.value in str(refused.value)


def test_accepting_unverified_with_the_dedicated_permission_is_allowed() -> None:
    stamped = stamped_trust({"unverified_reason": "lab link"}, actor_id=WHO, at=AT)

    stamped.refuse_unless_permitted(
        _Holding(Permission.INTEGRATION_MANAGE, Permission.INTEGRATION_TRUST_UNVERIFIED)
    )


# -- what is written, and that it survives the next write -------------------------


async def test_a_declaration_is_written_where_the_proxy_reads_it() -> None:
    gateway, scope = await _store(), TenantScope(org_id=ORG)

    await record_certificate_trust(
        gateway,
        scope=scope,
        node_id=ORG,
        integration="proxmox",
        trust=stamped_trust({"fingerprints": [COLONS]}, actor_id=WHO, at=AT),
        actor_id=WHO,
    )

    found = await configured_trust(gateway, scope=scope, node_id=ORG)
    assert found["proxmox"].anchor is TrustAnchor.PINNED_FINGERPRINT


async def test_the_declaration_survives_the_next_address_write() -> None:
    """The defect this exists to prevent: a fixed-field copy erases what it does not know."""
    from gateway.http.integration_endpoints import record_endpoint

    gateway, scope = await _store(), TenantScope(org_id=ORG)
    await record_certificate_trust(
        gateway,
        scope=scope,
        node_id=ORG,
        integration="proxmox",
        trust=stamped_trust({"fingerprints": [COLONS]}, actor_id=WHO, at=AT),
        actor_id=WHO,
    )

    await record_endpoint(
        gateway,
        scope=scope,
        node_id=ORG,
        integration="proxmox",
        base_url="https://pve02.lan.example:8006",
        actor_id=WHO,
    )

    found = await configured_trust(gateway, scope=scope, node_id=ORG)
    assert found["proxmox"].anchor is TrustAnchor.PINNED_FINGERPRINT, (
        "writing the address erased the trust declaration beside it. The entry copy "
        "carries a fixed set of fields, and one outside that set is gone at the first "
        "save afterwards."
    )
    # And it now covers the address it was moved to, because trust follows the
    # address rather than the vendor.
    assert found["proxmox"].addresses == ("pve02.lan.example",)


# -- the audit line ----------------------------------------------------------------


def test_the_audit_detail_names_who_when_which_addresses_and_which_form() -> None:
    stamped = stamped_trust(
        {"unverified_reason": "lab cluster on a link with no DNS"}, actor_id=WHO, at=AT
    )
    detail = trust_audit_detail("proxmox", stamped, addresses=("pve01.lan.example",))

    assert detail["integration"] == "proxmox"
    assert detail["anchor"] == TrustAnchor.UNVERIFIED.value
    assert detail["addresses"] == ["pve01.lan.example"]
    assert detail["accepted_by"] == WHO
    assert detail["accepted_at"] == AT.isoformat()
    assert detail["reason"]


def test_the_audit_detail_carries_the_fingerprints_because_they_are_not_secret() -> None:
    stamped = stamped_trust({"fingerprints": [COLONS]}, actor_id=WHO, at=AT)
    detail = trust_audit_detail("proxmox", stamped, addresses=("pve01.lan.example",))

    assert detail["fingerprints"] == [COLONS]


def test_no_certificate_material_reaches_the_audit_detail() -> None:
    stamped = stamped_trust({"certificate_pem": PEM}, actor_id=WHO, at=AT)
    detail = trust_audit_detail("proxmox", stamped, addresses=("pve01.lan.example",))

    written = repr(detail)
    assert "BEGIN CERTIFICATE" not in written
    assert "PRIVATE KEY" not in written
    assert "MIIBogIBADANBgkq" not in written


def test_the_audit_detail_is_a_fixed_set_of_scalars() -> None:
    """No route may add a field at the call site, which is how a body escapes into it."""
    stamped = stamped_trust({"fingerprints": [COLONS]}, actor_id=WHO, at=AT)
    detail = trust_audit_detail("proxmox", stamped, addresses=())

    assert set(detail) <= {
        "integration",
        "anchor",
        "addresses",
        "fingerprints",
        "reason",
        "accepted_by",
        "accepted_at",
    }
