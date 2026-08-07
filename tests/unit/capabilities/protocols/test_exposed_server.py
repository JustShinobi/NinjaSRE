"""SC-006: what NinjaSRE's own MCP server enforces, and what it flatly refuses.

The three claims: a token is required, its permissions and team scope are
enforced, and configuration, credentials, and remediation are refused by name
rather than by absence. Every one of them is asserted against the real
permission table and the real role catalogue rather than a mock that was taught
to agree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from capabilities.protocols.server.app import DISABLED_MESSAGE, McpServerApp, enabled_for
from capabilities.protocols.server.auth import ACCESS_REFUSED_MESSAGE
from capabilities.protocols.server.surface import (
    EXPOSED_TOOLS,
    OPERATION_PERMISSIONS,
    REFUSED_OPERATIONS,
    SurfaceOperation,
)
from config.constants.protocols import (
    MAX_EXPOSED_SURFACE_RESULTS,
    MCP_METHOD_CALL_TOOL,
    MCP_METHOD_INITIALIZE,
    MCP_METHOD_LIST_TOOLS,
    PROTOCOL_SERVER_AUDIT_ACTION,
)
from config.constants.surfaces import SURFACE_PROTOCOL_SERVER
from platform.config_service.schema.root import RootConfig
from platform.identity.authorisation import PermissionSet
from platform.identity.models import Grant
from platform.identity.permissions import Role
from platform.persistence.ports import AuditEvent, AuditOutcome, TenantScope

pytestmark = pytest.mark.unit


# --- doubles ---------------------------------------------------------------------


@dataclass(frozen=True)
class _Principal:
    id: str


@dataclass(frozen=True)
class _Token:
    principal: _Principal
    permissions: PermissionSet
    scope: TenantScope


class Authenticator:
    """Resolves exactly one secret, and refuses everything else."""

    def __init__(self, secret: str, token: _Token) -> None:
        self._secret = secret
        self._token = token

    async def authenticate(self, secret: str) -> _Token:
        if secret != self._secret:
            raise ValueError("no such token")
        return self._token


class Investigations:
    def __init__(self) -> None:
        self.started: list[tuple[str, str, str]] = []
        self.runs: dict[str, dict[str, Any]] = {}

    async def start(self, *, objective: str, service: str, team_id: str) -> str:
        self.started.append((objective, service, team_id))
        run_id = f"run-{len(self.started)}"
        self.runs[run_id] = {"run_id": run_id, "status": "running"}
        return run_id

    async def status(self, run_id: str, *, team_id: str) -> Mapping[str, Any] | None:
        return self.runs.get(run_id)

    async def result(self, run_id: str, *, team_id: str) -> Mapping[str, Any] | None:
        found = self.runs.get(run_id)
        return {"root_cause": "a bad deploy", "confidence": 0.8} if found else None


class Memory:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def search(self, query: str, *, team_id: str, limit: int) -> Sequence[Mapping[str, Any]]:
        self.limits.append(limit)
        return [{"summary": f"an episode about {query}"}]


class Topology:
    async def query(self, service: str, *, team_id: str, depth: int) -> Mapping[str, Any]:
        return {"service": service, "depends_on": ["postgres"], "depth": depth}


class Catalogue:
    async def capabilities(self, *, team_id: str) -> Sequence[Mapping[str, Any]]:
        return [{"name": "datadog_search_logs"}]


class RecordingRecorder:
    """Captures what the server audits, without a database."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def record(
        self,
        scope: TenantScope,
        context: Any,
        *,
        action: str,
        resource_kind: str,
        resource_id: str,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        detail: Mapping[str, Any] | None = None,
    ) -> AuditEvent | None:
        self.events.append(
            {
                "scope": scope,
                "action": action,
                "resource_id": resource_id,
                "outcome": outcome,
                "detail": dict(detail or {}),
            }
        )
        return None


SECRET = "token-value"


def _token(role: Role = Role.RESPONDER, *, team: str = "payments") -> _Token:
    return _Token(
        principal=_Principal(id="svc-composer"),
        permissions=PermissionSet(
            grants=(Grant(grant_id="g1", principal_id="svc-composer", role=role),)
        ),
        scope=TenantScope(org_id="acme", team_node_id=team),
    )


def _app(
    token: _Token | None = None,
    *,
    recorder: RecordingRecorder | None = None,
    enabled: bool = True,
    investigations: Investigations | None = None,
    memory: Memory | None = None,
) -> McpServerApp:
    return McpServerApp(
        authenticator=Authenticator(SECRET, token or _token()),
        investigations=investigations or Investigations(),
        memory=memory or Memory(),
        topology=Topology(),
        catalogue=Catalogue(),
        recorder=recorder,
        enabled=enabled,
    )


def _call(name: str, **arguments: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": MCP_METHOD_CALL_TOOL,
        "params": {"name": name, "arguments": arguments},
    }


def _text(frame: Mapping[str, Any]) -> str:
    return frame["result"]["content"][0]["text"]


# --- the surface is what it says it is --------------------------------------------


async def test_the_tool_list_is_the_six_exposed_operations_and_nothing_else() -> None:
    frame = await _app().handle({"jsonrpc": "2.0", "id": 1, "method": MCP_METHOD_LIST_TOOLS})

    names = {tool["name"] for tool in frame["result"]["tools"]}
    assert names == {operation.value for operation in SurfaceOperation}
    assert len(EXPOSED_TOOLS) == len(SurfaceOperation)


def test_every_exposed_operation_names_a_permission() -> None:
    assert set(OPERATION_PERMISSIONS) == set(SurfaceOperation)


async def test_initialise_names_the_protocol_and_the_server() -> None:
    frame = await _app().handle({"jsonrpc": "2.0", "id": 1, "method": MCP_METHOD_INITIALIZE})
    assert frame["result"]["serverInfo"]["name"] == "ninjasre"


# --- SC-006, first half: a token is required and its permissions are enforced ------


async def test_a_call_with_no_token_is_refused() -> None:
    frame = await _app().handle(_call("read_catalogue"))
    assert frame["result"]["isError"]
    assert _text(frame) == ACCESS_REFUSED_MESSAGE


async def test_a_call_with_the_wrong_token_is_refused_identically() -> None:
    frame = await _app().handle(_call("read_catalogue"), token="not-the-token")
    assert _text(frame) == ACCESS_REFUSED_MESSAGE


async def test_a_viewer_may_read_but_may_not_start_an_investigation() -> None:
    app = _app(_token(Role.VIEWER))

    reading = await app.handle(_call("read_catalogue"), token=SECRET)
    starting = await app.handle(
        _call("start_investigation", objective="why is it slow"), token=SECRET
    )

    assert not reading["result"]["isError"]
    assert starting["result"]["isError"]
    assert _text(starting) == ACCESS_REFUSED_MESSAGE


async def test_a_responder_may_start_an_investigation() -> None:
    investigations = Investigations()
    app = _app(_token(Role.RESPONDER), investigations=investigations)

    frame = await app.handle(
        _call("start_investigation", objective="checkout latency", service="checkout"),
        token=SECRET,
    )

    assert not frame["result"]["isError"]
    assert investigations.started == [("checkout latency", "checkout", "payments")]
    assert frame["result"]["structuredContent"]["run_id"] == "run-1"


async def test_a_token_scoped_to_one_team_cannot_address_another() -> None:
    app = _app(_token(Role.RESPONDER, team="payments"))

    frame = await app.handle(_call("read_catalogue", team_id="platform"), token=SECRET)

    assert frame["result"]["isError"]
    assert _text(frame) == ACCESS_REFUSED_MESSAGE


async def test_a_token_addressing_its_own_team_is_allowed() -> None:
    app = _app(_token(Role.RESPONDER, team="payments"))
    frame = await app.handle(_call("read_catalogue", team_id="payments"), token=SECRET)
    assert not frame["result"]["isError"]


# --- SC-006, second half: privileged operations are refused by name -----------------


@pytest.mark.parametrize("operation", sorted(REFUSED_OPERATIONS))
async def test_a_privileged_operation_is_refused_by_name_even_with_a_valid_token(
    operation: str,
) -> None:
    frame = await _app(_token(Role.OWNER)).handle(_call(operation), token=SECRET)

    assert frame["result"]["isError"]
    assert "read-and-investigate only" in _text(frame)


def test_the_refusal_list_covers_configuration_credentials_and_remediation() -> None:
    joined = " ".join(REFUSED_OPERATIONS.values())
    assert "configuration" in joined
    assert "credential" in joined
    assert "remediation" in joined


async def test_an_owner_token_still_cannot_reach_anything_beyond_the_six() -> None:
    # The most privileged role in the catalogue, and the surface is unchanged.
    frame = await _app(_token(Role.OWNER)).handle(_call("delete_organisation"), token=SECRET)
    assert frame["error"]["message"].startswith("'delete_organisation'")


# --- FR-017: every invocation is audited --------------------------------------------


async def test_an_allowed_invocation_is_audited() -> None:
    recorder = RecordingRecorder()
    app = _app(_token(Role.RESPONDER), recorder=recorder)

    await app.handle(_call("read_catalogue"), token=SECRET)

    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event["action"] == PROTOCOL_SERVER_AUDIT_ACTION
    assert event["resource_id"] == "read_catalogue"
    assert event["outcome"] is AuditOutcome.ALLOWED
    assert event["scope"].org_id == "acme"


async def test_a_refused_invocation_is_audited_as_loudly() -> None:
    recorder = RecordingRecorder()
    app = _app(_token(Role.VIEWER), recorder=recorder)

    await app.handle(_call("start_investigation", objective="anything"), token=SECRET)

    assert recorder.events[0]["outcome"] is AuditOutcome.DENIED
    assert "investigation.run" in recorder.events[0]["detail"]["reason"]


async def test_the_audit_records_argument_names_and_never_their_values() -> None:
    recorder = RecordingRecorder()
    app = _app(_token(Role.RESPONDER), recorder=recorder)

    await app.handle(
        _call("start_investigation", objective="customer 4711 cannot check out"), token=SECRET
    )

    detail = recorder.events[0]["detail"]
    assert detail["arguments"] == ["objective"]
    assert "4711" not in json.dumps(detail)


async def test_an_unauthenticated_call_writes_no_audit_row() -> None:
    # A caller with no valid token could otherwise write to the append-only
    # table at whatever rate they chose.
    recorder = RecordingRecorder()
    await _app(recorder=recorder).handle(_call("read_catalogue"), token="wrong")
    assert recorder.events == []


# --- bounds and behaviour ------------------------------------------------------------


async def test_a_read_is_bounded_whatever_the_caller_asks_for() -> None:
    memory = Memory()
    app = _app(_token(Role.RESPONDER), memory=memory)

    await app.handle(_call("search_memory", query="checkout", limit=10_000), token=SECRET)

    assert memory.limits == [MAX_EXPOSED_SURFACE_RESULTS]


async def test_a_run_this_team_cannot_read_is_indistinguishable_from_one_that_is_missing() -> None:
    frame = await _app(_token(Role.RESPONDER)).handle(
        _call("investigation_status", run_id="run-does-not-exist"), token=SECRET
    )
    assert frame["result"]["isError"]
    assert "no investigation this team can read" in _text(frame)


async def test_a_failing_operation_never_puts_a_stack_trace_on_the_wire() -> None:
    class Exploding(Topology):
        async def query(self, service: str, *, team_id: str, depth: int) -> Mapping[str, Any]:
            raise RuntimeError("the graph store is on fire")

    app = McpServerApp(
        authenticator=Authenticator(SECRET, _token(Role.RESPONDER)),
        investigations=Investigations(),
        memory=Memory(),
        topology=Exploding(),
        catalogue=Catalogue(),
    )

    frame = await app.handle(_call("query_topology", service="checkout"), token=SECRET)

    assert frame["result"]["isError"]
    assert "on fire" not in _text(frame)


# --- FR-020 / T039: optional, and inert when switched off ------------------------------


async def test_a_disabled_server_answers_nothing_and_says_so() -> None:
    frame = await _app(enabled=False).handle(
        {"jsonrpc": "2.0", "id": 1, "method": MCP_METHOD_LIST_TOOLS}
    )
    assert frame["error"]["message"] == DISABLED_MESSAGE


def test_a_deployment_that_does_not_enable_the_surface_has_no_listener() -> None:
    # Absence is off. A team that never mentions the protocol server gets none,
    # which is the direction a listener's default has to fail in.
    assert not enabled_for(RootConfig().surfaces)


def test_a_team_enables_the_surface_by_naming_it_like_any_other() -> None:
    config = RootConfig.of({"surfaces": {"enabled": ["cli", SURFACE_PROTOCOL_SERVER]}})
    assert enabled_for(config.surfaces)

    switched_off = RootConfig.of({"surfaces": {"enabled": ["cli"]}})
    assert not enabled_for(switched_off.surfaces)
