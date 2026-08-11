"""What a team's bridged servers offer, served where an operator can see it.

Everything needed to answer "what did this MCP server actually give the agent"
has existed for a while — discovery, the classification table, the health probe,
and ``bridged_catalogue`` composing all three. None of it was reachable from
outside the process. An operator classifying a tool was classifying a name they
had to already know.

The three properties this suite holds, and each is a way the screen could lie:

**A tool carries its origin.** Which server, which protocol, and the qualified
name the operator classifies against — not the flattened name the model calls,
which is a different string on purpose.

**An unreachable server is a reported absence.** Its tools vanish from the
catalogue, and the *reason* takes their place. A server that is down and a
server that offers nothing look identical from a tool list, and only one of them
is something anybody can fix.

**Unclassified is visible and is not executable.** A tool waiting on a decision
appears, says so, and is not offered — the console has to be able to show the
queue that the refusal is protecting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token
from httpx import ASGITransport, AsyncClient

from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ExcludedTool,
    ExclusionReason,
    ProtocolKind,
)
from gateway.http.app import create_app
from platform.config_service.service import ConfigService
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class StubAdapter:
    """A protocol adapter over fixed answers, counting what it was asked."""

    tools: dict[str, tuple[BridgedTool, ...]] = field(default_factory=dict)
    excluded: dict[str, tuple[ExcludedTool, ...]] = field(default_factory=dict)
    down: set[str] = field(default_factory=set)
    discoveries: list[str] = field(default_factory=list)

    @property
    def kind(self) -> ProtocolKind:
        """Return the protocol this stub claims to speak."""
        return ProtocolKind.MCP

    async def discover(self, server: str) -> Discovery:
        """Return what ``server`` offers, or nothing at all when it is down."""
        self.discoveries.append(server)
        if server in self.down:
            return Discovery(server=server)
        return Discovery(
            server=server,
            tools=self.tools.get(server, ()),
            excluded=self.excluded.get(server, ()),
        )

    async def describe(self, server: str, tool: str) -> BridgedTool | None:
        """Return one declaration; never reached by this suite."""
        return None

    async def invoke(self, server: str, tool: str, arguments: object) -> BridgedResult:
        """Never reached: this is a read surface."""
        raise AssertionError("the catalogue route must not invoke anything")

    async def health(self, server: str) -> BridgeHealth:
        """Return whether ``server`` answered."""
        if server in self.down:
            return BridgeHealth.down(server, "connection refused")
        return BridgeHealth.up(server)


def tool(server: str, name: str, *, declared: str = "read") -> BridgedTool:
    """Return one tool as a server declares it."""
    return BridgedTool(
        server=server,
        tool=name,
        description=f"{name} on {server}",
        declared_side_effect=declared,
    )


async def declare(
    deployment: Deployment,
    *,
    servers: tuple[dict[str, object], ...],
    classifications: dict[str, str] | None = None,
) -> None:
    """Write a team's bridged-server declaration into the configuration tree."""
    service = ConfigService(gateway=deployment.gateway, scope=TenantScope(org_id=ORG))
    await service.set_settings(
        TEAM_PAYMENTS,
        {
            "capabilities": {
                "protocol_servers": list(servers),
                "protocol_classifications": dict(classifications or {}),
            }
        },
        actor_id="ada",
    )


async def reader(deployment: Deployment) -> tuple[AsyncClient, dict[str, str]]:
    """Return a client and the headers of an operator who may read configuration."""
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ops",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )
    app = create_app(deployment.state)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")
    return client, {"Authorization": f"Bearer {secret}"}


async def test_a_bridged_tool_is_served_with_its_origin_and_its_classification(
    deployment: Deployment,
) -> None:
    deployment.state.protocol_adapter = StubAdapter(
        tools={"deploys": (tool("deploys", "list_deploys"),)}
    )
    await declare(
        deployment,
        servers=({"name": "deploys", "protocol": "mcp", "url": "https://deploys.test"},),
        classifications={"deploys.list_deploys": "read"},
    )

    client, headers = await reader(deployment)
    async with client:
        answer = await client.get("/v1/protocols/catalogue", headers=headers)

    assert answer.status_code == 200
    body = answer.json()
    [server] = body["servers"]
    assert server["server"] == "deploys"
    assert server["protocol"] == "mcp"
    assert server["reachable"] is True
    [entry] = server["tools"]
    assert entry["qualified_name"] == "deploys.list_deploys"
    assert entry["catalogue_name"] == "deploys__list_deploys"
    assert entry["classification"] == "read"
    assert entry["executable"] is True


async def test_a_server_that_did_not_answer_reports_why_instead_of_its_tools(
    deployment: Deployment,
) -> None:
    deployment.state.protocol_adapter = StubAdapter(down={"deploys"})
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        body = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    [server] = body["servers"]
    assert server["reachable"] is False
    assert "connection refused" in server["detail"]
    assert server["tools"] == []


async def test_an_unclassified_tool_is_shown_and_is_not_executable(
    deployment: Deployment,
) -> None:
    """The queue an operator works through; a refusal nobody can see is a mystery."""
    deployment.state.protocol_adapter = StubAdapter(
        tools={"deploys": (tool("deploys", "roll_out", declared="write"),)}
    )
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        body = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    [entry] = body["servers"][0]["tools"]
    assert entry["executable"] is False
    assert entry["awaiting_classification"] is True
    assert entry["declared_side_effect"] == "write"
    assert body["awaiting_classification"] == ["deploys.roll_out"]


async def test_an_excluded_tool_keeps_its_reason(deployment: Deployment) -> None:
    deployment.state.protocol_adapter = StubAdapter(
        tools={"deploys": (tool("deploys", "list_deploys"),)},
        excluded={
            "deploys": (
                ExcludedTool(
                    server="deploys",
                    tool="mystery",
                    reason=ExclusionReason.MALFORMED_SCHEMA,
                    detail="its input schema is not an object",
                ),
            )
        },
    )
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        body = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    [excluded] = body["excluded"]
    assert excluded["qualified_name"] == "deploys.mystery"
    assert "not an object" in excluded["detail"]


async def test_a_deployment_with_no_adapter_says_so_rather_than_serving_nothing(
    deployment: Deployment,
) -> None:
    """An empty catalogue and an unwired bridge look identical, and are not."""
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        body = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    assert body["servers"] == []
    assert body["unavailable_reason"]
    assert "deploys" in body["declared"]


async def test_a_team_that_declared_nothing_gets_an_empty_catalogue_and_no_alarm(
    deployment: Deployment,
) -> None:
    deployment.state.protocol_adapter = StubAdapter()

    client, headers = await reader(deployment)
    async with client:
        body = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    assert body["servers"] == []
    assert body["unavailable_reason"] == ""


# -- the caching policy --------------------------------------------------------


async def test_a_second_read_inside_the_window_does_not_contact_the_server_again(
    deployment: Deployment,
) -> None:
    """One operator refreshing a screen must not become a request per refresh."""
    adapter = StubAdapter(tools={"deploys": (tool("deploys", "list_deploys"),)})
    deployment.state.protocol_adapter = adapter
    deployment.state.protocol_catalogue_cache.clock = lambda: datetime(2026, 3, 2, tzinfo=UTC)
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        await client.get("/v1/protocols/catalogue", headers=headers)
        await client.get("/v1/protocols/catalogue", headers=headers)

    assert adapter.discoveries == ["deploys"]


async def test_the_window_expires_so_a_server_coming_back_is_noticed(
    deployment: Deployment,
) -> None:
    """A cache that never expired would keep showing an outage that ended."""
    adapter = StubAdapter(down={"deploys"})
    deployment.state.protocol_adapter = adapter
    moment = datetime(2026, 3, 2, tzinfo=UTC)
    deployment.state.protocol_catalogue_cache.clock = lambda: moment
    await declare(deployment, servers=({"name": "deploys", "url": "https://deploys.test"},))

    client, headers = await reader(deployment)
    async with client:
        first = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

        adapter.down.clear()
        adapter.tools["deploys"] = (tool("deploys", "list_deploys"),)
        moment = moment.replace(hour=1)
        deployment.state.protocol_catalogue_cache.clock = lambda: moment
        second = (await client.get("/v1/protocols/catalogue", headers=headers)).json()

    assert first["servers"][0]["reachable"] is False
    assert second["servers"][0]["reachable"] is True


async def test_the_cache_is_per_team_so_one_team_never_reads_another_s(
    deployment: Deployment,
) -> None:
    """A shared entry would show one team the servers another team registered."""
    cache = deployment.state.protocol_catalogue_cache
    assert cache.key(TenantScope(org_id=ORG, team_node_id="payments")) != cache.key(
        TenantScope(org_id=ORG, team_node_id="platform")
    )
