"""The six lifecycle points, and the one that can change what happens next.

Five of the six observe. ``pre_tool_use`` is the exception, and the exception is
the point of the design: masking rewrites arguments there, the approval gate
denies there, and a guardrail rule blocks there. Concentrating every
control-flow influence at one point keeps the security-relevant surface small
enough to audit — a hook that could inject calls from anywhere would make
"what can this run do" unanswerable.

Three results, and the absence of one:

``Allow``
    Proceed. Also what ``None`` means, so an observe-only hook does not have to
    import a result type to say it has no opinion.

``Deny``
    Do not run the call. The reason goes back to the model as a structured
    failure, so it can route around the refusal rather than repeat it.

``Rewrite``
    Run the call with different arguments. Later hooks see the rewritten
    arguments, which is what lets masking and a policy check compose.

A hook may not inject a new tool call. That is deliberate: a call nobody
requested would appear in the trace with no rationale behind it, and the
trajectory scorer would be reading a step the model never chose.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from core.agent.session import Session
from core.agent.turn import Turn
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityErrorClass, CapabilityResult
from core.llm.types import ToolCall


class HookPoint(StrEnum):
    """Where a hook attaches to the loop."""

    ON_RUN_START = "on_run_start"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    ON_TURN_END = "on_turn_end"
    ON_RUN_END = "on_run_end"
    ON_CANCEL = "on_cancel"


@dataclass(frozen=True, slots=True)
class ToolContext:
    """What a tool hook is told about the call it is looking at.

    The declaration travels with the call because that is what the interesting
    decisions are made on: masking cares about the argument schema, and the
    approval gate cares about the side-effect level, neither of which is
    recoverable from a name and a dictionary.
    """

    session: Session
    iteration: int
    registered: RegisteredTool

    @property
    def capability(self) -> str:
        """Return the name of the capability being called."""
        return self.registered.name


@dataclass(frozen=True, slots=True)
class Allow:
    """Proceed with the call as it stands."""


@dataclass(frozen=True, slots=True)
class Deny:
    """Refuse the call, and tell the model why in terms it can act on.

    ``APPROVAL_REQUIRED`` is the default because that is what denial is for in
    practice: an action above ``read_sensitive`` waiting on a human. A guardrail
    block passes ``PERMISSION_DENIED`` instead, and the difference matters to
    the model — one is worth waiting for and the other is not.
    """

    reason: str
    classification: CapabilityErrorClass = CapabilityErrorClass.APPROVAL_REQUIRED

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a denial must say why, or the model cannot route around it")


@dataclass(frozen=True, slots=True)
class Rewrite:
    """Proceed, with these arguments instead.

    Masking is the motivating case: the credential-shaped value is replaced by a
    handle before the call leaves the process, and nothing above this point ever
    holds the secret.
    """

    arguments: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""


#: What ``pre_tool_use`` may return. ``None`` is accepted too and means ``Allow``.
HookResult = Allow | Deny | Rewrite

#: The shared "no opinion" instance, so an allowing hook allocates nothing.
ALLOW = Allow()


class RunStartHook(Protocol):
    """Called once, before the first model turn."""

    async def __call__(self, session: Session) -> None:
        """Observe the start of ``session``."""


class PreToolUseHook(Protocol):
    """Called before every capability invocation, and able to change it."""

    async def __call__(self, call: ToolCall, context: ToolContext) -> HookResult | None:
        """Return what to do with ``call``, or ``None`` to allow it unchanged."""


class PostToolUseHook(Protocol):
    """Called after every capability invocation, and able to replace the result."""

    async def __call__(
        self, call: ToolCall, result: CapabilityResult, context: ToolContext
    ) -> CapabilityResult | None:
        """Return a replacement result, or ``None`` to keep ``result``."""


class TurnEndHook(Protocol):
    """Called once per completed iteration."""

    async def __call__(self, session: Session, turn: Turn) -> None:
        """Observe ``turn`` at the end of an iteration of ``session``."""


class RunEndHook(Protocol):
    """Called once, whatever the run's outcome."""

    async def __call__(self, session: Session, result: Any) -> None:
        """Observe the end of ``session`` and the result it produced."""


class CancelHook(Protocol):
    """Called when a run stops at a safe point after being cancelled."""

    async def __call__(self, session: Session) -> None:
        """Observe the cancellation of ``session``."""


__all__ = [
    "ALLOW",
    "Allow",
    "CancelHook",
    "Deny",
    "HookPoint",
    "HookResult",
    "PostToolUseHook",
    "PreToolUseHook",
    "Rewrite",
    "RunEndHook",
    "RunStartHook",
    "ToolContext",
    "TurnEndHook",
]
