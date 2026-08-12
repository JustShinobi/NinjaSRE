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
