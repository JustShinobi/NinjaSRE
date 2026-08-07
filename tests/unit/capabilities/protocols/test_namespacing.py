"""The grammar that makes a bridged name impossible to confuse with a native one.

Two collisions are being ruled out, and they are ruled out differently. Two
bridged tools cannot collide because the server-plus-tool pair maps injectively
onto the catalogue name — which needs the separator to be absent from every
server name. A bridged tool cannot collide with a *native* capability because no
native capability name contains the separator at all, and that is asserted here
against the shipped catalogue rather than assumed.
"""

from __future__ import annotations

import pytest

from capabilities.protocols.namespacing import (
    BridgedName,
    InvalidServerName,
    catalogue_name,
    is_bridged_name,
    parse_catalogue_name,
    qualified_name,
    validate_server_name,
)
from capabilities.registry.catalogue import build_registry
from config.constants.protocols import PROTOCOL_NAMESPACE_SEPARATOR


def test_a_bridged_name_joins_the_server_and_the_tool() -> None:
    assert catalogue_name("deploys", "rollout") == "deploys__rollout"
    assert qualified_name("deploys", "rollout") == "deploys.rollout"


def test_a_catalogue_name_is_a_legal_tool_name() -> None:
    from core.capability.metadata import TOOL_NAME_PATTERN

    assert TOOL_NAME_PATTERN.match(catalogue_name("deploys", "rollout"))


def test_a_third_party_tool_name_is_lowered_and_cleaned() -> None:
    # A server is entitled to call its tool whatever it likes. The catalogue is
    # not entitled to carry a name the provider dialects would rewrite.
    assert catalogue_name("deploys", "Roll-Out Now!") == "deploys__roll_out_now"


def test_a_tool_name_that_cleans_to_nothing_still_produces_a_distinct_name() -> None:
    first = catalogue_name("deploys", "***")
    second = catalogue_name("deploys", "???")
    assert first != second
    assert first.startswith("deploys__")


def test_a_name_round_trips_back_to_the_server_and_the_tool() -> None:
    parsed = parse_catalogue_name(catalogue_name("deploys", "rollout"))
    assert parsed == BridgedName(server="deploys", tool="rollout")


def test_a_tool_carrying_the_separator_still_round_trips_to_its_server() -> None:
    # Split on the first separator: the server may not contain one, the tool may.
    name = catalogue_name("deploys", "roll__out")
    assert parse_catalogue_name(name) == BridgedName(server="deploys", tool="roll__out")


def test_a_native_name_does_not_parse_as_a_bridged_one() -> None:
    assert parse_catalogue_name("datadog_search_logs") is None
    assert not is_bridged_name("datadog_search_logs")
    assert is_bridged_name("deploys__rollout")


def test_a_server_name_may_not_contain_the_separator() -> None:
    with pytest.raises(InvalidServerName) as raised:
        validate_server_name("my__server")
    assert PROTOCOL_NAMESPACE_SEPARATOR in str(raised.value)


def test_a_server_name_follows_the_tool_grammar() -> None:
    for rejected in ("", "Deploys", "9deploys", "deploys-1", "deploys.one"):
        with pytest.raises(InvalidServerName):
            validate_server_name(rejected)
    assert validate_server_name("deploys_1") == "deploys_1"


def test_no_native_capability_name_could_be_mistaken_for_a_bridged_one() -> None:
    # The other half of "collisions are structurally impossible". If this ever
    # fails, a native capability has taken a name the bridge can also produce.
    registry = build_registry()
    colliding = [name for name in registry.tools if is_bridged_name(name)]
    assert colliding == []
