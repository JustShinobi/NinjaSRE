"""Bridged servers as a team declares them, in the six-section schema.

A protocol server is a capability *source*, so it lives in the capabilities
section rather than becoming a seventh top-level one. The two things worth
asserting are that the shape is typed like everything else — no free-form
document — and that a team with no bridged servers is unaffected, which is what
FR-020 asks for.
"""

from __future__ import annotations

import pytest

from platform.config_service.schema.capabilities import CapabilitiesConfig
from platform.config_service.schema.root import RootConfig

pytestmark = pytest.mark.unit


def test_a_team_that_declares_no_servers_has_none() -> None:
    assert CapabilitiesConfig().protocol_servers == ()
    assert CapabilitiesConfig().protocol_classifications == {}
    assert RootConfig().capabilities.protocol_servers == ()


def test_a_server_is_declared_with_a_transport_and_an_address() -> None:
    config = RootConfig.of(
        {
            "capabilities": {
                "protocol_servers": [
                    {
                        "name": "deploys",
                        "protocol": "mcp",
                        "transport": "http",
                        "url": "https://mcp.example.test/rpc",
                    }
                ],
                "protocol_classifications": {"deploys.status": "read"},
            }
        }
    )

    server = config.capabilities.protocol_servers[0]
    assert server.name == "deploys"
    assert server.url == "https://mcp.example.test/rpc"
    assert server.enabled
    assert config.capabilities.protocol_classifications == {"deploys.status": "read"}


def test_a_stdio_server_is_declared_with_a_command() -> None:
    config = RootConfig.of(
        {
            "capabilities": {
                "protocol_servers": [
                    {"name": "local", "transport": "stdio", "command": ["mcp-local", "--stdio"]}
                ]
            }
        }
    )

    assert config.capabilities.protocol_servers[0].command == ("mcp-local", "--stdio")


def test_a_bridged_tool_name_is_not_cross_referenced_against_the_native_catalogue() -> None:
    # A classification names a tool that exists on somebody else's server. Feeding
    # it to the capability cross-reference check would report every bridged tool
    # as a dangling reference.
    config = RootConfig.of(
        {"capabilities": {"protocol_classifications": {"deploys.status": "read"}}}
    )
    assert "deploys.status" not in config.capability_references()


def test_a_disabled_server_is_still_declared_and_says_so() -> None:
    config = RootConfig.of(
        {
            "capabilities": {
                "protocol_servers": [
                    {"name": "deploys", "url": "https://mcp.example.test/rpc", "enabled": False}
                ]
            }
        }
    )
    assert not config.capabilities.protocol_servers[0].enabled
    assert config.capabilities.enabled_protocol_servers() == ()
