"""Which servers a team has, how they are reached, and what a refresh does.

The registration is where FR-006 becomes concrete: an HTTP server's credential
is a vault handle the proxy resolves, and this module produces the injection
rule and the egress allow-list from the same declaration, so widening one
widens the other.
"""

from __future__ import annotations

import pytest

from capabilities.protocols.classification import ClassificationTable
from capabilities.protocols.namespacing import InvalidServerName
from capabilities.protocols.port import ProtocolKind
from capabilities.protocols.registration import (
    AuthKind,
    ProtocolRegistry,
    RefreshOutcome,
    ServerRegistration,
    TransportKind,
    refresh_classifications,
    registrations_from_config,
)
from config.constants.protocols import MAX_PROTOCOL_SERVERS_PER_TEAM
from platform.config_service.schema.root import RootConfig

pytestmark = pytest.mark.unit


# --- declaring a server ----------------------------------------------------------


def test_an_http_server_needs_an_address() -> None:
    with pytest.raises(ValueError, match="url"):
        ServerRegistration(name="deploys", transport=TransportKind.HTTP)


def test_a_stdio_server_needs_a_command() -> None:
    with pytest.raises(ValueError, match="command"):
        ServerRegistration(name="deploys", transport=TransportKind.STDIO)


def test_a_server_name_that_cannot_namespace_a_tool_is_refused_at_registration() -> None:
    with pytest.raises(InvalidServerName):
        ServerRegistration(
            name="My Deploys", transport=TransportKind.HTTP, url="https://x.test/rpc"
        )


def test_an_http_server_must_be_reached_over_tls() -> None:
    with pytest.raises(ValueError, match="https"):
        ServerRegistration(
            name="deploys", transport=TransportKind.HTTP, url="http://mcp.example.test/rpc"
        )


def test_a_server_gets_its_own_credential_name_so_it_cannot_borrow_anothers() -> None:
    first = ServerRegistration(name="deploys", url="https://a.test/rpc")
    second = ServerRegistration(name="payments", url="https://b.test/rpc")
    assert first.integration != second.integration
    assert "deploys" in first.integration


def test_a_declared_credential_name_wins_over_the_derived_one() -> None:
    server = ServerRegistration(
        name="deploys", url="https://a.test/rpc", credential="shared_mcp_token"
    )
    assert server.integration == "shared_mcp_token"


# --- the credential proxy and the egress allow-list (FR-006, T045) ---------------


def test_an_authenticated_server_declares_an_injection_rule_naming_only_its_own_host() -> None:
    server = ServerRegistration(
        name="deploys", url="https://mcp.example.test/rpc", auth=AuthKind.BEARER
    )

    rule = server.injection_rule()

    assert rule is not None
    assert rule.integration == server.integration
    assert rule.hosts == ("mcp.example.test",)
    assert rule.permits("mcp.example.test")
    assert not rule.permits("elsewhere.example.test")


def test_a_header_authenticated_server_declares_the_header_it_wants() -> None:
    server = ServerRegistration(
        name="deploys",
        url="https://mcp.example.test/rpc",
        auth=AuthKind.HEADER,
        auth_header="X-Api-Key",
    )

    rule = server.injection_rule()

    assert rule is not None
    assert rule.required_fields() == ("token",)


def test_an_unauthenticated_server_declares_no_rule_and_still_declares_its_host() -> None:
    server = ServerRegistration(name="deploys", url="https://mcp.example.test/rpc")

    assert server.auth is AuthKind.NONE
    assert server.injection_rule() is None
    assert server.egress_hosts() == ("mcp.example.test",)


def test_a_stdio_server_reaches_nothing_over_the_network() -> None:
    server = ServerRegistration(name="local", transport=TransportKind.STDIO, command=("mcp-local",))
    assert server.egress_hosts() == ()
    assert server.injection_rule() is None


def test_a_stdio_server_may_not_be_given_a_credential() -> None:
    # There is nowhere to put it. A local process would need it in its
    # environment or its arguments, and Article IV forbids both.
    with pytest.raises(ValueError, match="stdio"):
        ServerRegistration(
            name="local",
            transport=TransportKind.STDIO,
            command=("mcp-local",),
            auth=AuthKind.BEARER,
        )


# --- reading a team's configuration -----------------------------------------------


def test_servers_come_from_the_teams_configuration() -> None:
    config = RootConfig.of(
        {
            "capabilities": {
                "protocol_servers": [
                    {"name": "deploys", "url": "https://mcp.example.test/rpc"},
                    {"name": "local", "transport": "stdio", "command": ["mcp-local"]},
                    {"name": "off", "url": "https://off.example.test/rpc", "enabled": False},
                ]
            }
        }
    )

    registrations = registrations_from_config(config.capabilities)

    assert [item.name for item in registrations] == ["deploys", "local"]
    assert registrations[1].transport is TransportKind.STDIO


def test_a_team_with_no_servers_registers_nothing() -> None:
    assert registrations_from_config(RootConfig().capabilities) == ()


def test_more_servers_than_the_cap_are_refused_rather_than_silently_truncated() -> None:
    servers = [
        {"name": f"s{index}", "url": f"https://s{index}.example.test/rpc"}
        for index in range(MAX_PROTOCOL_SERVERS_PER_TEAM + 1)
    ]
    config = RootConfig.of({"capabilities": {"protocol_servers": servers}})

    with pytest.raises(ValueError, match=str(MAX_PROTOCOL_SERVERS_PER_TEAM)):
        registrations_from_config(config.capabilities)


def test_a_server_configured_with_a_name_no_tool_could_carry_is_reported_not_crashed() -> None:
    config = RootConfig.of(
        {"capabilities": {"protocol_servers": [{"name": "Bad Name", "url": "https://x.test/rpc"}]}}
    )
    with pytest.raises(InvalidServerName):
        registrations_from_config(config.capabilities)


def test_classifications_come_from_the_same_place_as_the_servers() -> None:
    config = RootConfig.of(
        {
            "capabilities": {
                "protocol_servers": [{"name": "deploys", "url": "https://x.test/rpc"}],
                "protocol_classifications": {"deploys.status": "read"},
            }
        }
    )

    registry = ProtocolRegistry.from_config(config.capabilities)

    assert registry.classifications.is_classified("deploys.status")
    assert registry.servers_for(ProtocolKind.MCP) == ("deploys",)


# --- refresh (FR-013) --------------------------------------------------------------


def test_a_new_tool_arrives_unclassified() -> None:
    outcome = refresh_classifications(
        ClassificationTable.of({"deploys.status": "read"}),
        offered=("deploys.status", "deploys.rollout"),
    )

    assert outcome.added == ("deploys.rollout",)
    assert outcome.removed == ()
    assert outcome.classifications.is_classified("deploys.status")
    assert not outcome.classifications.is_classified("deploys.rollout")


def test_a_removed_tool_takes_its_classification_with_it() -> None:
    outcome = refresh_classifications(
        ClassificationTable.of({"deploys.status": "read", "deploys.gone": "read"}),
        offered=("deploys.status",),
    )

    assert outcome.removed == ("deploys.gone",)
    assert not outcome.classifications.is_classified("deploys.gone")


def test_a_tool_that_comes_back_after_being_removed_is_unclassified_again() -> None:
    first = refresh_classifications(ClassificationTable.of({"deploys.rollout": "read"}), offered=())
    second = refresh_classifications(first.classifications, offered=("deploys.rollout",))

    assert second.added == ("deploys.rollout",)
    assert not second.classifications.is_classified("deploys.rollout")


def test_an_unchanged_tool_set_changes_nothing() -> None:
    table = ClassificationTable.of({"deploys.status": "read"})
    outcome = refresh_classifications(table, offered=("deploys.status",))

    assert outcome == RefreshOutcome(
        added=(), removed=(), retained=("deploys.status",), classifications=outcome.classifications
    )
    assert outcome.classifications.is_classified("deploys.status")
