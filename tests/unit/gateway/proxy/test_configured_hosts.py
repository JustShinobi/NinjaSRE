"""The egress allow-list, extended by the addresses an operator configured.

An integration ships an allow-list of the hosts it may reach, and the shipped
entry is a placeholder — ``proxmox.example.com``. Nothing ever added the address
the operator actually configured, so a deployment that had stored its
credential, activated the integration and entered its endpoint was refused at
the proxy with "may not reach 192.168.68.159".

The allow-list is the right design and stays. What was missing is that
declaring where your cluster is *is* the declaration: the configuration tree is
where an operator says it, with provenance and a preview, and the proxy has to
read it.
"""

from __future__ import annotations

import pytest

from gateway.proxy.hosts import hosts_from_configuration, with_configured_hosts
from integrations.proxmox.schema import RULE as PROXMOX_RULE
from platform.credentials.proxy.injection import InjectionRuleRegistry

pytestmark = pytest.mark.unit


def _registry() -> InjectionRuleRegistry:
    registry = InjectionRuleRegistry()
    registry.register(PROXMOX_RULE)
    return registry


def test_the_configured_address_joins_the_shipped_allow_list() -> None:
    """Joins rather than replaces: the shipped host stays permitted."""
    registry = _registry()
    shipped = set(registry.get("proxmox").hosts)

    with_configured_hosts(registry, {"proxmox": ("192.168.68.159",)})

    permitted = set(registry.get("proxmox").hosts)
    assert "192.168.68.159" in permitted
    assert shipped <= permitted


def test_a_host_is_taken_from_the_address_an_operator_entered() -> None:
    """An operator configures a URL; an allow-list entry is a host."""
    assert hosts_from_configuration(
        [{"name": "proxmox", "enabled": True, "base_url": "https://192.168.68.159:8006/"}]
    ) == {"proxmox": ("192.168.68.159",)}


def test_a_disabled_integration_contributes_no_host() -> None:
    """Switching an integration off must close the egress it opened."""
    assert (
        hosts_from_configuration(
            [{"name": "proxmox", "enabled": False, "base_url": "https://pve.invalid:8006/"}]
        )
        == {}
    )


def test_an_entry_with_no_address_contributes_nothing() -> None:
    assert hosts_from_configuration([{"name": "proxmox", "enabled": True, "base_url": ""}]) == {}


def test_an_integration_nothing_declares_is_ignored_rather_than_registered() -> None:
    """A rule invented here would permit egress no integration asked for."""
    registry = _registry()

    with_configured_hosts(registry, {"nosuchvendor": ("host.invalid",)})

    assert not registry.has("nosuchvendor")


def test_a_port_is_not_part_of_the_allow_list_entry() -> None:
    """The rule refuses a host:port, and says why — so this must strip it."""
    assert hosts_from_configuration(
        [{"name": "proxmox", "enabled": True, "base_url": "https://pve.lan:8006"}]
    ) == {"proxmox": ("pve.lan",)}


async def test_the_proxy_installs_the_encryption_key_before_it_checks_it() -> None:
    """The same defect the application had, in the process that resolves secrets.

    The proxy is the only thing that decrypts a credential, and nothing loaded
    the key into its ring. Its own start-up check for undecryptable credentials
    passed — with no key there is nothing to try — and then every forwarded call
    failed with "the key differs from the one that wrote it".
    """
    import os
    from unittest.mock import patch

    from gateway.proxy.__main__ import install_encryption_key
    from platform.persistence.postgres.crypto import KEY_RING

    KEY_RING.clear()
    try:
        with patch.dict(
            os.environ, {"NINJASRE_DATABASE_ENCRYPTION_KEY": "0" * 43 + "="}, clear=False
        ):
            assert install_encryption_key() is True
        assert KEY_RING.is_configured
    finally:
        KEY_RING.clear()


# --- The trust store, and an appliance's own certificate authority -------------


def test_the_system_store_alone_stays_strict() -> None:
    """A deployment that named no bundle verifies public vendors as strictly as
    the standard library does."""
    from gateway.proxy.sender import trust_context

    context = trust_context({})

    import ssl

    assert bool(context.verify_flags & ssl.VERIFY_X509_STRICT)


def test_an_operators_own_bundle_relaxes_only_the_rfc_5280_strictness(
    tmp_path: object,
) -> None:
    """Python 3.13 turned on VERIFY_X509_STRICT, which requires a CA to carry
    keyUsage=keyCertSign,cRLSign. An appliance that mints its own — Proxmox
    does — predictably does not, so every call to the operator's own cluster
    fails with "CA cert does not include key usage extension".

    Naming a bundle is the operator's decision about their own infrastructure,
    so that is where the flag is dropped. Chain building and hostname checking
    stay on: this is not verify=False, which the module deliberately has no
    setting for.
    """
    import ssl
    from pathlib import Path

    from gateway.proxy.sender import trust_context

    bundle = Path(str(tmp_path)) / "appliance-ca.pem"
    bundle.write_text(_SELF_SIGNED_CA, encoding="utf8")

    context = trust_context({"NINJASRE_CA_BUNDLE": str(bundle)})

    assert not (context.verify_flags & ssl.VERIFY_X509_STRICT)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


#: A certificate authority with no keyUsage extension, which is the shape of the
#: thing an appliance mints for itself and the shape RFC 5280 strictness
#: refuses. Generated once and committed, so this test needs no openssl.
_SELF_SIGNED_CA = """-----BEGIN CERTIFICATE-----
MIIDGTCCAgGgAwIBAgIUbFkGOaTqc3A3rvsdkgVWqSzVKoMwDQYJKoZIhvcNAQEL
BQAwHDEaMBgGA1UEAwwRdGVzdC1hcHBsaWFuY2UtY2EwHhcNMjYwODEyMDcyODE1
WhcNMzYwODA5MDcyODE1WjAcMRowGAYDVQQDDBF0ZXN0LWFwcGxpYW5jZS1jYTCC
ASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAMfSSvQFoBcLXokUMISH2sUd
T5fI7vFa5aiFYEgTS4ms6Uwa2J+ezN92Qp5z/OpDirssXQipDdM1DhZ3QnguQOsV
RdLGkzPU892cJgf5hbyqIqScicK+COaXyFn4i1xsCL405rBDM4SXrYGChB1oI+Aa
Ouxj/KClUx2cO/rBDrrj1yNF2HKWpIwI+xYWtgaUxO7APWorgr/aFzZhOTlvShVr
P1BQXlocodSAWU9ygpgP2ywykKdYYvzhB9zAyiDQjdsIBgNQYK7WesJs2M4rYVJi
t9/Ba2AYSJok116n/Q+9FrZexzfATlH2FJH1MTAe2wVqUKroBd/8RU5DESgmgYMC
AwEAAaNTMFEwHQYDVR0OBBYEFMNWeMuvBZySbJOE9RprWJ7GxqSzMB8GA1UdIwQY
MBaAFMNWeMuvBZySbJOE9RprWJ7GxqSzMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZI
hvcNAQELBQADggEBAI2BfCKVgSfUNtiljVvYpCp70yw/tZOQMQ1SLMBh0qp+Csgb
a/1+2MFJJymDkPayzNAzz4b2GhwLpINF99FVtaxflyRfo5vmRVDcl8ny3DxEfjNj
x4ezZqs0Knld9B+yCAlFJ8LucpnDQvSPnnfxK854yYWOBkw88w/QL+v56NAr9OQw
A/MzNb8j/ImnjRDu7gA00iqRjZoE+juI4GUoTx3NBlNu9v45Uyzd7vub7hcwKc5U
zuaihH5AgDB6vnDKbrqftlZ5bUj6VJpn6bLzpTzfpq6y0gTd1PObros3YEZdJA3h
Tu0EH34Gp5koJOuHwl6fy3E9H0MqD8jESV9T1Sg=
-----END CERTIFICATE-----
"""
