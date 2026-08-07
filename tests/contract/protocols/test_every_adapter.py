"""One suite, run once per protocol: the port, and the governance over it.

The argument for a port is that a fourth protocol costs one adapter and no
governance. That is only true if the governance is asserted over every adapter
rather than over the one somebody happened to write tests for — so this suite is
parameterised over all three, and adding a protocol adds a row here rather than
a file.

FR-020 is the other half: both ACP and OpenClaw are optional, and a deployment
that enables neither is unaffected. Asserted at the bottom, against a real
configuration document with no protocol servers in it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from capabilities.protocols.acp.adapter import AGENTS_PATH, RUNS_PATH, AcpAdapter
from capabilities.protocols.catalogue import bridged_catalogue
from capabilities.protocols.classification import ClassificationTable
from capabilities.protocols.mcp.adapter import McpAdapter
from capabilities.protocols.openclaw.adapter import (
    CAPABILITIES_PATH,
    OpenClawAdapter,
)
from capabilities.protocols.port import ExclusionReason, MalformedServerResponse, ProtocolAdapter
from capabilities.protocols.registration import ProtocolRegistry, registrations_from_config
from capabilities.registry.catalogue import build_registry
from config.constants.protocols import MCP_METHOD_CALL_TOOL, MCP_METHOD_LIST_TOOLS
from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass
from platform.config_service.schema.root import RootConfig

pytestmark = pytest.mark.contract

SERVER = "peer"
ANSWER = "the thing the peer said"

OBJECT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"target": {"type": "string"}},
    "required": ["target"],
}


# --- one scripted far side per protocol -------------------------------------------


class ScriptedMcpTransport:
    """An MCP server that lists two tools and answers a call."""

    def __init__(self, *, reachable: bool = True, broken_tool: bool = False) -> None:
        self.reachable = reachable
        self.broken_tool = broken_tool
        self.invocations: list[Mapping[str, Any]] = []

    @property
    def server(self) -> str:
        return SERVER

    async def request(
        self, method: str, params: Mapping[str, Any], *, timeout_seconds: float = 5.0
    ) -> Any:
        if not self.reachable:
            raise MalformedServerResponse(f"{SERVER} is not answering")
        if method == MCP_METHOD_LIST_TOOLS:
            tools = [
                {"name": "look", "description": "Look.", "inputSchema": dict(OBJECT_SCHEMA)},
                {"name": "change", "description": "Change.", "inputSchema": dict(OBJECT_SCHEMA)},
            ]
            if self.broken_tool:
                tools.append({"name": "broken", "inputSchema": {"type": "object", "properties": 1}})
            return {"tools": tools}
        if method == MCP_METHOD_CALL_TOOL:
            self.invocations.append(dict(params.get("arguments", {})))
            return {"content": [{"type": "text", "text": ANSWER}]}
        return {}

    async def close(self) -> None:
        return None


class ScriptedPeer:
    """An ACP or OpenClaw peer, answering the two documents each protocol reads."""

    def __init__(
        self,
        *,
        listing_path: str,
        entries_key: str,
        schema_key: str,
        reachable: bool = True,
        broken_tool: bool = False,
    ) -> None:
        self._listing_path = listing_path
        self._entries_key = entries_key
        self._schema_key = schema_key
        self.reachable = reachable
        self.broken_tool = broken_tool
        self.invocations: list[Mapping[str, Any]] = []

    @property
    def server(self) -> str:
        return SERVER

    async def get_json(self, path: str, *, timeout_seconds: float = 5.0) -> Any:
        if not self.reachable:
            raise MalformedServerResponse(f"{SERVER} is not answering")
        assert path == self._listing_path
        entries: list[dict[str, Any]] = [
            {"name": "look", "description": "Look.", self._schema_key: dict(OBJECT_SCHEMA)},
            {"name": "change", "description": "Change.", self._schema_key: dict(OBJECT_SCHEMA)},
        ]
        if self.broken_tool:
            entries.append(
                {"name": "broken", self._schema_key: {"type": "object", "properties": 1}}
            )
        return {self._entries_key: entries}

    async def post_json(
        self, path: str, payload: Mapping[str, Any], *, timeout_seconds: float = 5.0
    ) -> Any:
        if not self.reachable:
            raise MalformedServerResponse(f"{SERVER} is not answering")
        if path == RUNS_PATH:
            self.invocations.append(dict(payload.get("input", {})))
            return {"status": "completed", "output": ANSWER}
        self.invocations.append(dict(payload.get("arguments", {})))
        return {"result": ANSWER}

    async def close(self) -> None:
        return None


def _mcp(**kwargs: Any) -> tuple[ProtocolAdapter, ScriptedMcpTransport]:
    transport = ScriptedMcpTransport(**kwargs)
    return McpAdapter({SERVER: transport}), transport


def _acp(**kwargs: Any) -> tuple[ProtocolAdapter, ScriptedPeer]:
    peer = ScriptedPeer(
        listing_path=AGENTS_PATH, entries_key="agents", schema_key="input", **kwargs
    )
    return AcpAdapter({SERVER: peer}), peer


def _openclaw(**kwargs: Any) -> tuple[ProtocolAdapter, ScriptedPeer]:
    source = ScriptedPeer(
        listing_path=CAPABILITIES_PATH,
        entries_key="capabilities",
        schema_key="parameters",
        **kwargs,
    )
    return OpenClawAdapter({SERVER: source}), source


BUILDERS: Mapping[str, Callable[..., tuple[ProtocolAdapter, Any]]] = {
    "mcp": _mcp,
    "acp": _acp,
    "openclaw": _openclaw,
}
PROTOCOLS: Sequence[str] = tuple(BUILDERS)


async def _catalogue(adapter: ProtocolAdapter, classifications: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return await bridged_catalogue(
        adapter,
        servers=(SERVER,),
        classifications=ClassificationTable.of(classifications or {}),
    )


# --- the port ----------------------------------------------------------------------


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_every_adapter_satisfies_the_port(protocol: str) -> None:
    adapter, _ = BUILDERS[protocol]()
    assert isinstance(adapter, ProtocolAdapter)
    assert adapter.kind.value == protocol


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_adapter_discovers_describes_and_reports_health(protocol: str) -> None:
    adapter, _ = BUILDERS[protocol]()

    discovery = await adapter.discover(SERVER)
    described = await adapter.describe(SERVER, "look")
    health = await adapter.health(SERVER)

    assert [item.tool for item in discovery.tools] == ["look", "change"]
    assert described is not None and described.qualified_name == "peer.look"
    assert health.reachable


# --- the governance over it -----------------------------------------------------------


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocols_tools_are_namespaced_by_server(protocol: str) -> None:
    adapter, _ = BUILDERS[protocol]()

    built = await _catalogue(adapter)

    assert {found.catalogue_name for found in built.capabilities} == {"peer__look", "peer__change"}


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocols_unclassified_tools_cannot_execute(protocol: str) -> None:
    adapter, far_side = BUILDERS[protocol]()

    built = await _catalogue(adapter)
    result = await built.capability("peer.change").registered.invoke({"target": "web"})

    assert not built.capability("peer.change").executable
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert far_side.invocations == []


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocols_classified_tools_run_and_produce_evidence(protocol: str) -> None:
    adapter, far_side = BUILDERS[protocol]()

    built = await _catalogue(adapter, {"peer.look": "read"})
    result = await built.capability("peer.look").registered.invoke({"target": "web"})

    assert result.succeeded
    assert far_side.invocations == [{"target": "web"}]
    assert result.evidence[0].source == SERVER
    assert ANSWER in json.dumps(result.value)


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocols_classified_write_carries_its_approval_metadata(
    protocol: str,
) -> None:
    adapter, _ = BUILDERS[protocol]()

    built = await _catalogue(adapter, {"peer.change": "write_reversible"})
    metadata = built.capability("peer.change").registered.metadata

    assert metadata.side_effect_level is SideEffectLevel.WRITE_REVERSIBLE
    assert metadata.requires_approval
    assert metadata.rollback_plan.strip()


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocol_excludes_a_malformed_declaration_and_keeps_the_rest(
    protocol: str,
) -> None:
    adapter, _ = BUILDERS[protocol](broken_tool=True)

    built = await _catalogue(adapter)

    assert {found.tool for found in built.capabilities} == {"look", "change"}
    assert [item.reason for item in built.excluded] == [ExclusionReason.MALFORMED_SCHEMA]


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocol_degrades_when_its_far_side_is_down(protocol: str) -> None:
    adapter, _ = BUILDERS[protocol](reachable=False)

    built = await _catalogue(adapter, {"peer.look": "read"})

    assert built.capabilities == ()
    assert built.unhealthy == (SERVER,)
    assert not (await adapter.health(SERVER)).reachable


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_every_protocol_reports_a_server_it_does_not_hold_rather_than_raising(
    protocol: str,
) -> None:
    adapter, _ = BUILDERS[protocol]()

    result = await adapter.invoke("not_registered", "look", {})

    assert result.error_class is CapabilityErrorClass.UNAVAILABLE
    assert (await adapter.discover("not_registered")).tools == ()


# --- FR-020: optional, and inert when nobody enables them --------------------------------


def test_a_deployment_that_enables_no_protocol_registers_nothing() -> None:
    config = RootConfig()

    registry = ProtocolRegistry.from_config(config.capabilities)

    assert registrations_from_config(config.capabilities) == ()
    assert not registry
    assert registry.injection_rules() == ()
    assert registry.egress_hosts() == ()
    for kind in ("mcp", "acp", "openclaw"):
        assert registry.servers_for(_kind(kind)) == ()


async def test_a_deployment_that_enables_no_protocol_has_an_empty_bridged_catalogue() -> None:
    adapter, _ = _mcp()

    built = await bridged_catalogue(adapter, servers=())

    assert built.capabilities == ()
    assert built.excluded == ()
    assert built.unhealthy == ()
    assert built.report() == ""


def test_the_native_catalogue_is_unchanged_by_the_bridge_existing() -> None:
    # The strongest version of "does not affect a deployment that does not
    # enable them": the shipped catalogue contains no bridged capability, and
    # no capability of the bridge's own.
    registry = build_registry()
    assert not any("__" in name for name in registry.tools)
    assert not any(name.startswith("bridge") for name in registry.tools)


def _kind(value: str):  # type: ignore[no-untyped-def]
    from capabilities.protocols.port import ProtocolKind

    return ProtocolKind(value)
