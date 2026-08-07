"""SC-001 and SC-004, driven through the real credential proxy and the real loop.

The far side here is an actual MCP server — it parses JSON-RPC frames off the
wire and answers them — rather than a stubbed adapter, and it is reached through
a real ``ProxyEngine`` holding a real vault entry. That is what makes the two
interesting assertions mean something: the agent invoked a bridged tool during an
investigation (SC-001), and the credential that authenticated the call was never
anywhere the agent could see it (FR-006).

The server is in-process because there is no third-party MCP server this suite
may reach — a test that needs the network is a test that is skipped, and a
skipped test is not a criterion. What is *not* faked is the part under test:
the frames, the proxy, the injection, the egress allow-list, the catalogue, the
classification gate, and the loop.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from capabilities.protocols.catalogue import bridged_catalogue
from capabilities.protocols.classification import ClassificationTable
from capabilities.protocols.mcp.adapter import McpAdapter
from capabilities.protocols.mcp.client import HttpMcpTransport
from capabilities.protocols.registration import (
    BRIDGE_CREDENTIAL_FIELD,
    AuthKind,
    ProtocolRegistry,
    registrations_from_config,
)
from config.constants.protocols import (
    JSON_RPC_VERSION,
    MCP_METHOD_CALL_TOOL,
    MCP_METHOD_INITIALIZE,
    MCP_METHOD_LIST_TOOLS,
    MCP_METHOD_PING,
)
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest
from core.capability.telemetry import record_invocation
from core.llm.types import ToolCall
from integrations._base.transport import InProcessProxyTransport, RequestContext
from platform.config_service.schema.root import RootConfig
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialField, CredentialSchema, CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from tests.unit.core.agent.conftest import ScriptedLLM, call_turn, text_turn

pytestmark = pytest.mark.contract

ORG_ID = "acme"
TEAM_ID = "payments"
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
SERVER_HOST = "mcp.deploys.example"
SERVER_URL = f"https://{SERVER_HOST}/rpc"

#: The value in the vault. Made up, and the suite asserts it never appears
#: anywhere the agent can read.
SECRET_TOKEN = "bridge-secret-4c1f9a"

TEAM_CONFIG = {
    "capabilities": {
        "protocol_servers": [
            {
                "name": "deploys",
                "protocol": "mcp",
                "transport": "http",
                "url": SERVER_URL,
                "credential": "bridge_deploys",
            }
        ],
        "protocol_classifications": {"deploys.recent_rollouts": "read"},
    }
}


class McpServerBehindTheProxy:
    """An ``OutboundSender`` that is a real MCP server on the other side.

    Parses the frame it is sent and answers it. What it records is what the
    proxy actually put on the wire — including the ``Authorization`` header the
    injection added, which is how the credential half of this suite is checked.
    """

    def __init__(self, *, reachable: bool = True) -> None:
        self.reachable = reachable
        self.sent: list[OutboundRequest] = []

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        self.sent.append(request)
        if not self.reachable:
            return OutboundResponse(503, {}, b"upstream unavailable")

        frame = json.loads(request.body or b"{}")
        method = frame.get("method")
        identifier = frame.get("id")

        if method == MCP_METHOD_INITIALIZE:
            return _frame(identifier, {"protocolVersion": "2025-06-18", "capabilities": {}})
        if method == MCP_METHOD_PING:
            return _frame(identifier, {})
        if method == MCP_METHOD_LIST_TOOLS:
            return _frame(identifier, {"tools": [_RECENT_ROLLOUTS, _RESTART_SERVICE]})
        if method == MCP_METHOD_CALL_TOOL:
            arguments = frame.get("params", {}).get("arguments", {})
            return _frame(
                identifier,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"3 rollouts of {arguments.get('service')} in the last hour",
                        }
                    ]
                },
            )
        return _frame(identifier, {}, error={"code": -32601, "message": "no such method"})

    @property
    def authorisations(self) -> list[str]:
        """Return every ``Authorization`` header the server actually received."""
        return [
            value
            for request in self.sent
            for name, value in request.headers.items()
            if name.lower() == "authorization"
        ]


_RECENT_ROLLOUTS: Mapping[str, Any] = {
    "name": "recent_rollouts",
    "description": "List the deployments of a service in the last hour.",
    "inputSchema": {
        "type": "object",
        "properties": {"service": {"type": "string"}},
        "required": ["service"],
    },
    "annotations": {"readOnlyHint": True},
}

_RESTART_SERVICE: Mapping[str, Any] = {
    "name": "restart_service",
    "description": "Restart a service.",
    "inputSchema": {"type": "object", "properties": {"service": {"type": "string"}}},
    # The server says this is read-only. It is not, and its saying so changes
    # nothing — which is the whole argument for operator classification.
    "annotations": {"readOnlyHint": True},
}


def _frame(
    identifier: Any, result: Mapping[str, Any], *, error: Mapping[str, Any] | None = None
) -> OutboundResponse:
    payload: dict[str, Any] = {"jsonrpc": JSON_RPC_VERSION, "id": identifier}
    if error is not None:
        payload["error"] = dict(error)
    else:
        payload["result"] = dict(result)
    return OutboundResponse(
        200, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8")
    )


async def _stand_up(*, reachable: bool = True) -> tuple[McpAdapter, McpServerBehindTheProxy]:
    """Return an adapter reaching one bridged server through a real proxy."""
    registry = ProtocolRegistry.from_config(RootConfig.of(TEAM_CONFIG).capabilities)
    registration = registry.registration("deploys")
    assert registration is not None
    # The configuration named a credential, so the registration authenticates.
    assert registration.auth is AuthKind.BEARER

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schema = CredentialSchema(
        integration=registration.integration,
        fields=(CredentialField(name=BRIDGE_CREDENTIAL_FIELD, description="the server's token"),),
    )
    schemas = CredentialSchemaRegistry.from_schemas(schema)
    vault = Vault(gateway=gateway, schemas=schemas)
    await vault.store(
        SCOPE,
        CredentialHandle(integration=registration.integration, team_id=TEAM_ID),
        {BRIDGE_CREDENTIAL_FIELD: SECRET_TOKEN},
    )

    server = McpServerBehindTheProxy(reachable=reachable)
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*registry.injection_rules()),
        sender=server,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )
    transport = HttpMcpTransport(
        server="deploys",
        transport=InProcessProxyTransport(create_proxy_app(engine)),
        context=RequestContext(
            org_id=ORG_ID, team_id=TEAM_ID, capability="deploys__recent_rollouts"
        ),
        url=SERVER_URL,
        integration=registration.integration,
    )
    return McpAdapter({"deploys": transport}), server


async def _catalogue(adapter: McpAdapter):  # type: ignore[no-untyped-def]
    capabilities = RootConfig.of(TEAM_CONFIG).capabilities
    return await bridged_catalogue(
        adapter,
        servers=tuple(item.name for item in registrations_from_config(capabilities)),
        classifications=ClassificationTable.of(dict(capabilities.protocol_classifications)),
    )


# --- SC-001: registered tools appear and are invocable -----------------------------


async def test_a_registered_servers_tools_appear_in_the_catalogue() -> None:
    adapter, _ = await _stand_up()

    built = await _catalogue(adapter)

    assert {found.catalogue_name for found in built.capabilities} == {
        "deploys__recent_rollouts",
        "deploys__restart_service",
    }
    assert built.capability("deploys.recent_rollouts").executable
    # Declared read-only by the server, classified by nobody: still inert.
    assert not built.capability("deploys.restart_service").executable
    assert built.awaiting_classification() == ("deploys.restart_service",)


async def test_the_agent_invokes_a_bridged_tool_during_an_investigation() -> None:
    adapter, server = await _stand_up()
    built = await _catalogue(adapter)
    tools = tuple(built.executable_tools().values())

    loop = ReActLoop(
        llm=ScriptedLLM(
            [
                call_turn(
                    ToolCall(
                        id="c1",
                        name="deploys__recent_rollouts",
                        arguments={"service": "checkout"},
                    )
                ),
                text_turn("Three rollouts in the last hour explain the latency."),
            ],
            repeat_last=False,
        ),
        tools=tools,
    )

    result = await loop.run(RunRequest(objective="why is checkout slow"))

    execution = result.turns[0].executions[0]
    assert execution.capability == "deploys__recent_rollouts"
    assert not execution.denied
    assert "3 rollouts of checkout" in result.session.evidence[0].content
    assert result.session.evidence[0].source == "deploys"


async def test_the_credential_reached_the_server_and_never_the_agent() -> None:
    adapter, server = await _stand_up()
    built = await _catalogue(adapter)

    outcome = await built.capability("deploys.recent_rollouts").registered.invoke(
        {"service": "checkout"}
    )

    assert outcome.succeeded
    # The proxy attached it at the edge, on every call it made — the discovery
    # listing as well as the invocation.
    assert server.authorisations
    assert set(server.authorisations) == {f"Bearer {SECRET_TOKEN}"}
    # …and nothing above the proxy ever held it: not the answer, not the
    # declaration the model is shown, not the trace record.
    registered = built.capability("deploys.recent_rollouts").registered
    assert SECRET_TOKEN not in json.dumps(outcome.value)
    assert SECRET_TOKEN not in json.dumps(dict(registered.input_schema))
    assert SECRET_TOKEN not in registered.metadata.description
    assert SECRET_TOKEN not in json.dumps(
        (await record_invocation(registered, {"service": "checkout"})).to_record()
    )


def test_a_host_the_server_did_not_declare_is_outside_its_allow_list() -> None:
    # T045: the registration's URL is the allow-list, and the proxy enforces it
    # before a credential is decrypted.
    registry = ProtocolRegistry.from_config(RootConfig.of(TEAM_CONFIG).capabilities)
    rule = registry.injection_rules()[0]

    assert rule.hosts == (SERVER_HOST,)
    assert not rule.permits("somewhere-else.example")


# --- SC-004: an unavailable server degrades rather than fails ------------------------


async def test_an_unavailable_server_leaves_the_catalogue_empty_and_says_why() -> None:
    adapter, _ = await _stand_up(reachable=False)

    built = await _catalogue(adapter)

    assert built.capabilities == ()
    assert built.unhealthy == ("deploys",)
    assert "unavailable" in built.report()


async def test_an_investigation_still_runs_when_a_bridged_server_is_down() -> None:
    adapter, _ = await _stand_up(reachable=False)
    built = await _catalogue(adapter)

    loop = ReActLoop(
        llm=ScriptedLLM([text_turn("Nothing bridged was available; here is what I know.")]),
        tools=tuple(built.executable_tools().values()),
    )

    result = await loop.run(RunRequest(objective="why is checkout slow"))

    assert result.answer
    assert result.turns


async def test_a_server_that_goes_down_between_refreshes_excludes_only_its_own_tools() -> None:
    healthy, _ = await _stand_up()
    before = await _catalogue(healthy)
    assert len(before.capabilities) == 2

    broken, _ = await _stand_up(reachable=False)
    after = await _catalogue(broken)

    assert after.capabilities == ()
    assert after.unhealthy == ("deploys",)


# --- what the console reads (T032) --------------------------------------------------


async def test_the_console_can_show_servers_tools_and_classification_status() -> None:
    adapter, _ = await _stand_up()

    built = await _catalogue(adapter)

    rows: Sequence[tuple[str, str, bool, str]] = tuple(
        (
            found.server,
            found.qualified_name,
            found.executable,
            found.classification.suggested_level.value,
        )
        for found in built.capabilities
    )
    assert ("deploys", "deploys.recent_rollouts", True, "read") in rows
    assert ("deploys", "deploys.restart_service", False, "read") in rows
    assert built.report()
