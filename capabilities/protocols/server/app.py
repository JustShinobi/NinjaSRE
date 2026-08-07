"""NinjaSRE as an MCP server: the frames in, the six operations, the audit line.

The point of exposing anything at all is composition — a coding agent that has
just broken a deploy should be able to ask NinjaSRE what happened without a
human copying an incident id between two windows. The point of exposing almost
nothing is that this is a listener, and a listener is an attack surface whether
or not anyone meant it to be.

So: read and investigate, token-scoped, and audited whatever the outcome. The
audit is written for a refusal as loudly as for a success, because a token
failing against this surface twice a second is the event most worth seeing and
it is exactly the one a success-only trail would miss.

**Off unless a team asked for it.** ``protocol_server`` is one of the surface
identifiers a team's configuration enables, and ``enabled_for`` reads it — so a
deployment that never mentions it has no listener, and one that wants it quiet
during an incident edits configuration rather than redeploying. A disabled app
answers every frame with the same refusal rather than pretending the operations
are missing, because "this deployment switched it off" and "you are talking to
the wrong version" send an operator to different places.

Deliberately *not* an environment variable. ``capabilities/`` does not read the
process environment at all — its configuration comes from the hierarchy and its
credentials from the proxy, so a lookup here would be one or the other in the
wrong place.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from capabilities.protocols.server.auth import (
    AccessRefused,
    SurfaceCaller,
    TokenAuthenticator,
    audit_detail,
    authenticate,
    authorise,
)
from capabilities.protocols.server.surface import (
    EXPOSED_TOOLS,
    OPERATION_PERMISSIONS,
    CatalogueSurface,
    InvestigationSurface,
    MemorySurface,
    SurfaceOperation,
    TopologySurface,
    bounded_limit,
    refusal_for,
)
from config.constants.protocols import (
    JSON_RPC_VERSION,
    MCP_METHOD_CALL_TOOL,
    MCP_METHOD_INITIALIZE,
    MCP_METHOD_LIST_TOOLS,
    MCP_METHOD_PING,
    MCP_PROTOCOL_VERSION,
    PROTOCOL_SERVER_AUDIT_ACTION,
    PROTOCOL_SERVER_AUDIT_RESOURCE_KIND,
)
from config.constants.surfaces import SURFACE_PROTOCOL_SERVER
from platform.config_service.schema.surfaces import SurfacesConfig
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.observability.logging import get_logger
from platform.persistence.ports import ActorKind, AuditOutcome

logger = get_logger(__name__)

#: What NinjaSRE tells a connecting client about itself.
SERVER_INFO: Final[Mapping[str, str]] = {"name": "ninjasre", "version": "1"}

#: JSON-RPC's own codes, for the two cases this server produces.
METHOD_NOT_FOUND: Final[int] = -32601
INVALID_PARAMS: Final[int] = -32602

#: What every frame is told when the server is composed but switched off.
DISABLED_MESSAGE: Final = "NinjaSRE's protocol server is disabled in this deployment."


def enabled_for(surfaces: SurfacesConfig) -> bool:
    """Return whether a team's configuration enables the protocol server.

    Absence is off. A listener nobody enumerated is a listener nobody is
    watching, and that is the wrong direction for a default to fail in.
    """
    return SURFACE_PROTOCOL_SERVER in surfaces.enabled


@dataclass(frozen=True, slots=True)
class SurfaceOutcome:
    """One handled call: what to answer, and what the audit trail records."""

    payload: Mapping[str, Any]
    is_error: bool = False
    audited_outcome: AuditOutcome = AuditOutcome.ALLOWED
    audited_reason: str = ""


class McpServerApp:
    """The MCP server NinjaSRE exposes, over whatever transport a deployment mounts.

    Frames in, frames out, and no transport of its own. A deployment mounts this
    behind its HTTP stack or wires it to stdin; the governance is the same
    either way, which is the only way to keep it the same.
    """

    __slots__ = (
        "_authenticator",
        "_catalogue",
        "_enabled",
        "_investigations",
        "_memory",
        "_recorder",
        "_topology",
    )

    def __init__(
        self,
        *,
        authenticator: TokenAuthenticator,
        investigations: InvestigationSurface,
        memory: MemorySurface,
        topology: TopologySurface,
        catalogue: CatalogueSurface,
        recorder: AuditRecorder | None = None,
        enabled: bool = True,
    ) -> None:
        self._authenticator = authenticator
        self._investigations = investigations
        self._memory = memory
        self._topology = topology
        self._catalogue = catalogue
        self._recorder = recorder
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Return whether this server answers anything."""
        return self._enabled

    async def handle(self, frame: Mapping[str, Any], *, token: str = "") -> dict[str, Any]:
        """Return the JSON-RPC frame answering ``frame``.

        Never raises. A listener that can be made to throw is a listener whose
        error handling is somebody else's, and a stack trace on the wire is a
        map of the deployment.
        """
        identifier = frame.get("id")
        method = str(frame.get("method", ""))

        if not self._enabled:
            return _error(identifier, METHOD_NOT_FOUND, DISABLED_MESSAGE)

        if method == MCP_METHOD_INITIALIZE:
            return _result(
                identifier,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": dict(SERVER_INFO),
                },
            )
        if method == MCP_METHOD_PING:
            return _result(identifier, {})
        if method == MCP_METHOD_LIST_TOOLS:
            return _result(identifier, {"tools": [tool.declaration() for tool in EXPOSED_TOOLS]})
        if method == MCP_METHOD_CALL_TOOL:
            return await self._call(identifier, frame.get("params"), token=token)

        return _error(identifier, METHOD_NOT_FOUND, f"{method!r} is not a method this server has")

    async def _call(self, identifier: Any, params: Any, *, token: str) -> dict[str, Any]:
        """Return the answer to one ``tools/call``, audited whatever it is."""
        if not isinstance(params, Mapping):
            return _error(identifier, INVALID_PARAMS, "tools/call needs a params object")

        name = str(params.get("name", ""))
        arguments = params.get("arguments")
        arguments = arguments if isinstance(arguments, Mapping) else {}

        refused = refusal_for(name)
        if refused is not None:
            await self._audit_anonymous(name, refused)
            return _result(identifier, _content(refused, is_error=True))

        try:
            operation = SurfaceOperation(name)
        except ValueError:
            return _error(identifier, INVALID_PARAMS, f"{name!r} is not an operation this offers")

        try:
            caller = await authenticate(self._authenticator, token)
        except AccessRefused as refusal:
            await self._audit_anonymous(name, refusal.reason)
            return _result(identifier, _content(str(refusal), is_error=True))

        try:
            authorise(
                caller,
                operation=operation.value,
                permission=OPERATION_PERMISSIONS[operation],
                team_id=str(arguments.get("team_id", "") or ""),
            )
        except AccessRefused as refusal:
            await self._audit(caller, operation, arguments, refusal=refusal.reason)
            return _result(identifier, _content(str(refusal), is_error=True))

        outcome = await self._dispatch(caller, operation, arguments)
        await self._audit(
            caller,
            operation,
            arguments,
            refusal=outcome.audited_reason if outcome.is_error else "",
        )
        return _result(identifier, outcome.payload)

    async def _dispatch(
        self, caller: SurfaceCaller, operation: SurfaceOperation, arguments: Mapping[str, Any]
    ) -> SurfaceOutcome:
        """Return what one authorised operation produced."""
        team = caller.team_id
        try:
            if operation is SurfaceOperation.START_INVESTIGATION:
                objective = str(arguments.get("objective", "")).strip()
                if not objective:
                    return _refusal("start_investigation needs an objective")
                run_id = await self._investigations.start(
                    objective=objective,
                    service=str(arguments.get("service", "")),
                    team_id=team,
                )
                return SurfaceOutcome(payload=_content(run_id, structured={"run_id": run_id}))

            if operation is SurfaceOperation.INVESTIGATION_STATUS:
                found = await self._investigations.status(
                    str(arguments.get("run_id", "")), team_id=team
                )
                return _found_or_missing(found, "investigation")

            if operation is SurfaceOperation.INVESTIGATION_RESULT:
                found = await self._investigations.result(
                    str(arguments.get("run_id", "")), team_id=team
                )
                return _found_or_missing(found, "result")

            if operation is SurfaceOperation.SEARCH_MEMORY:
                episodes = await self._memory.search(
                    str(arguments.get("query", "")),
                    team_id=team,
                    limit=bounded_limit(arguments.get("limit")),
                )
                return SurfaceOutcome(payload=_content_list(list(episodes)))

            if operation is SurfaceOperation.QUERY_TOPOLOGY:
                graph = await self._topology.query(
                    str(arguments.get("service", "")),
                    team_id=team,
                    depth=bounded_limit(arguments.get("depth")),
                )
                return SurfaceOutcome(payload=_content_structured(dict(graph)))

            capabilities = await self._catalogue.capabilities(team_id=team)
            return SurfaceOutcome(payload=_content_list(list(capabilities)))
        except Exception as error:  # noqa: BLE001 — a listener never throws on the wire
            logger.warning(
                "protocols.server.operation_failed", operation=operation.value, error=str(error)
            )
            return _refusal(f"{operation.value} could not be completed")

    async def _audit(
        self,
        caller: SurfaceCaller,
        operation: SurfaceOperation,
        arguments: Mapping[str, Any],
        *,
        refusal: str = "",
    ) -> None:
        """Record one external invocation, allowed or denied (FR-017)."""
        if self._recorder is None:
            return
        detail = audit_detail(caller, operation=operation.value, arguments=arguments)
        if refusal:
            detail["reason"] = refusal
        await self._recorder.record(
            caller.scope,
            AuditContext(actor_kind=ActorKind.TOKEN, actor_id=caller.principal_id),
            action=PROTOCOL_SERVER_AUDIT_ACTION,
            resource_kind=PROTOCOL_SERVER_AUDIT_RESOURCE_KIND,
            resource_id=operation.value,
            outcome=AuditOutcome.DENIED if refusal else AuditOutcome.ALLOWED,
            detail=detail,
        )

    async def _audit_anonymous(self, name: str, reason: str) -> None:
        """Log a refusal that could not be attributed to a principal.

        Deliberately not an audit row. A caller with no valid token can write to
        the audit table at whatever rate they choose if this writes one, and the
        identity layer already declines to store unplaceable rejections for the
        same reason.
        """
        logger.warning("protocols.server.refused", operation=name, reason=reason)


def _result(identifier: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-RPC success frame."""
    return {"jsonrpc": JSON_RPC_VERSION, "id": identifier, "result": dict(payload)}


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    """Return a JSON-RPC error frame."""
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def _content(
    text: str, *, is_error: bool = False, structured: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return one ``tools/call`` result carrying ``text``."""
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if structured is not None:
        payload["structuredContent"] = dict(structured)
    return payload


def _content_structured(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return one result carrying a structured document and its rendering."""
    return _content(_render(value), structured=dict(value))


def _content_list(values: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Return one result carrying a list of records."""
    return _content(_render({"results": values}), structured={"results": values})


def _found_or_missing(found: Mapping[str, Any] | None, what: str) -> SurfaceOutcome:
    """Return the record, or a refusal that does not say whether it exists elsewhere."""
    if found is None:
        return _refusal(f"no {what} this team can read answers to that identifier")
    return SurfaceOutcome(payload=_content_structured(dict(found)))


def _refusal(message: str) -> SurfaceOutcome:
    """Return the outcome for a call that produced nothing usable."""
    return SurfaceOutcome(
        payload=_content(message, is_error=True),
        is_error=True,
        audited_outcome=AuditOutcome.DENIED,
        audited_reason=message,
    )


def _render(value: Any) -> str:
    """Return ``value`` as the text an external client reads."""
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


__all__ = [
    "DISABLED_MESSAGE",
    "INVALID_PARAMS",
    "METHOD_NOT_FOUND",
    "SERVER_INFO",
    "McpServerApp",
    "SurfaceOutcome",
    "enabled_for",
]
