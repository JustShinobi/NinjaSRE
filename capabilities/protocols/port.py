"""The four operations every protocol bridge has, and the values they pass.

Four, and the list is closed: **discover** what a server offers, **describe** one
of its tools, **invoke** one, and report **health**. MCP, ACP, and OpenClaw
differ in their wire format and in nothing above it, so anything a particular
protocol needs beyond these is configuration its adapter was constructed with.
A fifth method is how a protocol-specific escape hatch gets added and then
depended on, at which point "bridged capabilities are governed identically"
stops being true for one of them.

Two shapes are worth the paragraph.

**Discovery returns exclusions as values, not as an absence.** A server offering
two hundred tools where sixty-four are allowed, or a tool whose schema no
provider can be given, is a fact an operator can act on — and it looks exactly
like a server that offers nothing if the answer is a shorter list. So
``Discovery`` carries both what came through and what did not, each with a
reason, in the same way a team's resolved catalogue does.

**An invocation returns a value even when it failed.** The same discipline the
capability layer already keeps: a bridged server going down is one call's
failure, classified, and never an exception that ends the turn. Health is the
same shape for the same reason — a server that is unreachable is reported,
never raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from capabilities.protocols.namespacing import catalogue_name, qualified_name
from core.capability.result import CapabilityErrorClass


class ProtocolBridgeError(Exception):
    """A bridge could not do what it was asked, in a way worth naming.

    Deliberately rare. Almost everything that goes wrong with a third-party
    server is a value — an exclusion with a reason, a failed result, an
    unhealthy report — because those keep an investigation running. This is for
    the cases where the *configuration* is wrong rather than the server, which
    is a thing to fix rather than to degrade around.
    """


class MalformedServerResponse(ProtocolBridgeError):
    """A server answered in a shape the protocol does not allow.

    Specific on purpose (FR-012). "The server returned something odd" sends an
    operator to the wrong place; "the server's tools/list entry 3 has no name"
    sends them to the server's own logs with a question it can answer.
    """


class MalformedToolSchema(ProtocolBridgeError):
    """A declared tool's input schema is not one a model could ever be given."""


class ProtocolKind(StrEnum):
    """Which wire protocol a bridge speaks."""

    MCP = "mcp"
    ACP = "acp"
    OPENCLAW = "openclaw"


class ExclusionReason(StrEnum):
    """Why a tool a server offered is not in the catalogue.

    A closed set, because the console groups by it and an operator's next action
    differs per member: a capped server needs a narrower server, an
    unnormalisable schema needs the server's author, and an unreachable server
    needs the network.
    """

    SERVER_UNAVAILABLE = "server_unavailable"
    TOOL_CAP_REACHED = "tool_cap_reached"
    MALFORMED_SCHEMA = "malformed_schema"
    UNNORMALISABLE_SCHEMA = "unnormalisable_schema"
    DUPLICATE_NAME = "duplicate_name"
    DISABLED_FOR_TEAM = "disabled_for_team"


@dataclass(frozen=True, slots=True)
class BridgedTool:
    """One tool a server declares, before anything here has decided about it.

    ``declared_side_effect`` is what the server said about itself. It is carried
    so an operator can see it and never so anything can act on it — see
    ``classification.py`` for the argument.
    """

    server: str
    tool: str
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    declared_side_effect: str = ""
    title: str = ""

    @property
    def qualified_name(self) -> str:
        """Return the ``<server>.<tool>`` an operator reads and classifies against."""
        return qualified_name(self.server, self.tool)

    @property
    def catalogue_name(self) -> str:
        """Return the name the model would call this tool by."""
        return catalogue_name(self.server, self.tool)


@dataclass(frozen=True, slots=True)
class ExcludedTool:
    """A tool that was offered and is not available, and why."""

    server: str
    tool: str
    reason: ExclusionReason
    detail: str = ""

    @property
    def qualified_name(self) -> str:
        """Return the ``<server>.<tool>`` this exclusion is about."""
        return qualified_name(self.server, self.tool)

    def sentence(self) -> str:
        """Return a line the console can show an operator without further work."""
        base = f"{self.qualified_name}: {self.reason.value.replace('_', ' ')}"
        return f"{base} — {self.detail}" if self.detail else base


@dataclass(frozen=True, slots=True)
class Discovery:
    """What one server contributed, and what it did not.

    ``offered`` is what the server listed before any of our rules applied, so
    "sixty-four of two hundred" is answerable without re-contacting it.
    """

    server: str
    tools: tuple[BridgedTool, ...] = ()
    excluded: tuple[ExcludedTool, ...] = ()
    offered: int = 0

    def __post_init__(self) -> None:
        accounted = len(self.tools) + len(self.excluded)
        if self.offered < accounted:
            object.__setattr__(self, "offered", accounted)

    @property
    def excess(self) -> int:
        """Return how many offered tools did not make it into the catalogue."""
        return max(self.offered - len(self.tools), 0)

    def report(self) -> str:
        """Return the sentence the console shows about this server's contribution."""
        if not self.excess:
            return f"{self.server}: {len(self.tools)} tools"
        return f"{self.server}: {len(self.tools)} of {self.offered} tools, {self.excess} excluded"


@dataclass(frozen=True, slots=True)
class BridgeHealth:
    """Whether a server answered, and what it said if it did not.

    A value rather than an exception because an unreachable server must degrade
    the catalogue rather than fail the investigation (FR-007), and the code that
    degrades has to be able to say why in the console.
    """

    server: str
    reachable: bool
    detail: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency_seconds: float = 0.0

    @classmethod
    def up(cls, server: str, *, latency_seconds: float = 0.0) -> BridgeHealth:
        """Return the healthy report for ``server``."""
        return cls(server=server, reachable=True, latency_seconds=latency_seconds)

    @classmethod
    def down(cls, server: str, detail: str) -> BridgeHealth:
        """Return the unhealthy report for ``server``, carrying why."""
        return cls(server=server, reachable=False, detail=detail)


@dataclass(frozen=True, slots=True)
class BridgedResult:
    """What one bridged invocation produced.

    ``content`` is data. Never instructions, never a prompt fragment, never
    something a caller may act on because it says so — the guardrail engine sees
    it on the way back and the model sees it as a tool result like any other
    (FR-010).
    """

    value: Any = None
    failed: bool = False
    error_class: CapabilityErrorClass | None = None
    message: str = ""
    detail: str = ""
    truncated: bool = False
    duration_seconds: float = 0.0

    @classmethod
    def ok(
        cls, value: Any, *, truncated: bool = False, duration_seconds: float = 0.0
    ) -> BridgedResult:
        """Return a successful result carrying ``value``."""
        return cls(value=value, truncated=truncated, duration_seconds=duration_seconds)

    @classmethod
    def failure(
        cls,
        error_class: CapabilityErrorClass,
        message: str,
        *,
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> BridgedResult:
        """Return a classified failure the loop can reason about."""
        return cls(
            failed=True,
            error_class=error_class,
            message=message,
            detail=detail,
            duration_seconds=duration_seconds,
        )

    @property
    def succeeded(self) -> bool:
        """Return whether this invocation produced a usable result."""
        return not self.failed


@runtime_checkable
class ProtocolAdapter(Protocol):
    """One protocol, four operations, and no way to reach around them."""

    @property
    def kind(self) -> ProtocolKind:
        """Return which wire protocol this adapter speaks."""

    async def discover(self, server: str) -> Discovery:
        """Return the tools ``server`` offers, with everything excluded and why.

        Never raises for an unreachable server: a bridge that could fail a
        catalogue build could fail an investigation, and FR-007 says it must not.
        """

    async def describe(self, server: str, tool: str) -> BridgedTool | None:
        """Return one tool's declaration, or ``None`` when the server has no such tool."""

    async def invoke(self, server: str, tool: str, arguments: Mapping[str, Any]) -> BridgedResult:
        """Return what one call produced, with failure classified rather than raised."""

    async def health(self, server: str) -> BridgeHealth:
        """Return whether ``server`` is answering, and what it said if not."""


__all__ = [
    "BridgeHealth",
    "BridgedResult",
    "BridgedTool",
    "Discovery",
    "ExcludedTool",
    "ExclusionReason",
    "MalformedServerResponse",
    "MalformedToolSchema",
    "ProtocolAdapter",
    "ProtocolBridgeError",
    "ProtocolKind",
]
