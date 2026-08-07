"""What NinjaSRE offers another agent, and the much longer list of what it does not.

Six operations: start an investigation, read its status, read its result, search
episodic memory, query service topology, read the capability catalogue. A
composing agent may ask NinjaSRE *what is wrong*. It may not ask it to change
anything, and it may not ask it anything about credentials.

The refusals are named rather than left as unknown-tool errors (FR-016). An
agent asking for ``write_config`` should be told that this surface is
read-and-investigate only, because "unknown tool" reads as a version mismatch
and sends whoever wrote that agent looking for a newer NinjaSRE. It also makes
SC-006 assertable against the thing an attacker would actually try rather than
against a list this file happens to contain.

Every operation is a port. This package is tier 2 and an investigation runtime
is a deployment concern, so the surface holds protocols and a composition root
supplies the implementations — the same seam the CLI and the REST API already
use for exactly the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.protocols import MAX_EXPOSED_SURFACE_RESULTS
from platform.identity.permissions import Permission


class SurfaceOperation(StrEnum):
    """The exposed operations. Closed: adding one is a decision, not a patch."""

    START_INVESTIGATION = "start_investigation"
    INVESTIGATION_STATUS = "investigation_status"
    INVESTIGATION_RESULT = "investigation_result"
    SEARCH_MEMORY = "search_memory"
    QUERY_TOPOLOGY = "query_topology"
    READ_CATALOGUE = "read_catalogue"


#: What each operation is checked against, from the same permission table the
#: REST API uses. One table, so a permission that stops being enough somewhere
#: stops being enough here in the same edit.
OPERATION_PERMISSIONS: Final[Mapping[SurfaceOperation, Permission]] = {
    SurfaceOperation.START_INVESTIGATION: Permission.INVESTIGATION_RUN,
    SurfaceOperation.INVESTIGATION_STATUS: Permission.INVESTIGATION_READ,
    SurfaceOperation.INVESTIGATION_RESULT: Permission.INVESTIGATION_READ,
    SurfaceOperation.SEARCH_MEMORY: Permission.MEMORY_READ,
    SurfaceOperation.QUERY_TOPOLOGY: Permission.KNOWLEDGE_READ,
    SurfaceOperation.READ_CATALOGUE: Permission.CONFIG_READ,
}

#: Operations an external client might reasonably ask for and will never get,
#: each with the sentence explaining why. Names an agent would plausibly try,
#: because a refusal only helps if it is the one they hit.
REFUSED_OPERATIONS: Final[Mapping[str, str]] = {
    "set_config": "configuration is not writable through the protocol surface",
    "write_config": "configuration is not writable through the protocol surface",
    "update_config": "configuration is not writable through the protocol surface",
    "read_credential": "no surface of NinjaSRE reveals a credential, and no code path does",
    "get_credential": "no surface of NinjaSRE reveals a credential, and no code path does",
    "list_credentials": "credentials are not readable through the protocol surface",
    "store_credential": "credentials are not writable through the protocol surface",
    "execute_remediation": "remediation is not executable through the protocol surface",
    "run_remediation": "remediation is not executable through the protocol surface",
    "rollback": "remediation is not executable through the protocol surface",
    "approve_change": "approval decisions belong to a human in NinjaSRE's own surfaces",
    "reject_change": "approval decisions belong to a human in NinjaSRE's own surfaces",
    "issue_token": "identity and tokens are not manageable through the protocol surface",
    "revoke_token": "identity and tokens are not manageable through the protocol surface",
    "create_user": "identity and tokens are not manageable through the protocol surface",
}

#: What a refused operation is told, with the specific reason appended.
REFUSAL_MESSAGE: Final = "NinjaSRE's protocol surface is read-and-investigate only: {reason}."


@runtime_checkable
class InvestigationSurface(Protocol):
    """Starting an investigation and reading what it produced."""

    async def start(self, *, objective: str, service: str, team_id: str) -> str:
        """Return the identifier of a newly started investigation."""

    async def status(self, run_id: str, *, team_id: str) -> Mapping[str, Any] | None:
        """Return one run's status, or ``None`` when this team has no such run."""

    async def result(self, run_id: str, *, team_id: str) -> Mapping[str, Any] | None:
        """Return one run's finding, or ``None`` when it has not produced one."""


@runtime_checkable
class MemorySurface(Protocol):
    """Searching what previous investigations learned."""

    async def search(self, query: str, *, team_id: str, limit: int) -> Sequence[Mapping[str, Any]]:
        """Return the episodes matching ``query``, newest first."""


@runtime_checkable
class TopologySurface(Protocol):
    """Reading the service graph."""

    async def query(self, service: str, *, team_id: str, depth: int) -> Mapping[str, Any]:
        """Return what ``service`` depends on and what depends on it."""


@runtime_checkable
class CatalogueSurface(Protocol):
    """Reading what this deployment can do."""

    async def capabilities(self, *, team_id: str) -> Sequence[Mapping[str, Any]]:
        """Return the capability declarations this team can run."""


@dataclass(frozen=True, slots=True)
class ExposedTool:
    """One operation as an external MCP client sees it."""

    operation: SurfaceOperation
    description: str
    input_schema: Mapping[str, Any]

    def declaration(self) -> dict[str, Any]:
        """Return this operation as an MCP ``tools/list`` entry."""
        return {
            "name": self.operation.value,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            # Everything except starting an investigation is a read. Declaring
            # it is a courtesy to whoever is composing us — and, unlike a
            # third-party server's hint, it happens to be true.
            "annotations": {
                "readOnlyHint": self.operation is not SurfaceOperation.START_INVESTIGATION
            },
        }


def _object(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required)}


_TEXT = {"type": "string"}

#: The six declarations, written once. An external client reads these and this
#: is the whole of what it may ask for.
EXPOSED_TOOLS: Final[tuple[ExposedTool, ...]] = (
    ExposedTool(
        operation=SurfaceOperation.START_INVESTIGATION,
        description=(
            "Start a NinjaSRE investigation into a production problem and return its "
            "run identifier. The investigation runs asynchronously; poll "
            "investigation_status for progress."
        ),
        input_schema=_object(
            {"objective": _TEXT, "service": _TEXT},
            required=("objective",),
        ),
    ),
    ExposedTool(
        operation=SurfaceOperation.INVESTIGATION_STATUS,
        description="Return the current status of a NinjaSRE investigation.",
        input_schema=_object({"run_id": _TEXT}, required=("run_id",)),
    ),
    ExposedTool(
        operation=SurfaceOperation.INVESTIGATION_RESULT,
        description=(
            "Return a finished investigation's root cause, the evidence behind it, and "
            "its confidence."
        ),
        input_schema=_object({"run_id": _TEXT}, required=("run_id",)),
    ),
    ExposedTool(
        operation=SurfaceOperation.SEARCH_MEMORY,
        description="Search what previous investigations learned about a component or symptom.",
        input_schema=_object(
            {"query": _TEXT, "limit": {"type": "integer"}},
            required=("query",),
        ),
    ),
    ExposedTool(
        operation=SurfaceOperation.QUERY_TOPOLOGY,
        description="Return a service's dependencies and dependents from the topology graph.",
        input_schema=_object(
            {"service": _TEXT, "depth": {"type": "integer"}},
            required=("service",),
        ),
    ),
    ExposedTool(
        operation=SurfaceOperation.READ_CATALOGUE,
        description="Return the capabilities this NinjaSRE deployment can bring to an incident.",
        input_schema=_object({}),
    ),
)


def refusal_for(name: str) -> str | None:
    """Return why ``name`` is refused, or ``None`` when it is not a named refusal."""
    reason = REFUSED_OPERATIONS.get(name.strip().lower())
    return REFUSAL_MESSAGE.format(reason=reason) if reason else None


def bounded_limit(requested: Any) -> int:
    """Return a result limit inside the cap, whatever the caller asked for.

    A composing agent's context is not ours to spend. An absent, unreadable, or
    enormous limit all resolve to the cap rather than to an error: the caller
    wanted results, and refusing the call over a number is unhelpful when
    there is one right answer.
    """
    try:
        wanted = int(requested)
    except (TypeError, ValueError):
        return MAX_EXPOSED_SURFACE_RESULTS
    if wanted < 1:
        return MAX_EXPOSED_SURFACE_RESULTS
    return min(wanted, MAX_EXPOSED_SURFACE_RESULTS)


__all__ = [
    "EXPOSED_TOOLS",
    "OPERATION_PERMISSIONS",
    "REFUSAL_MESSAGE",
    "REFUSED_OPERATIONS",
    "CatalogueSurface",
    "ExposedTool",
    "InvestigationSurface",
    "MemorySurface",
    "SurfaceOperation",
    "TopologySurface",
    "bounded_limit",
    "refusal_for",
]
