"""Ordered dispatch, with a hook's failure recorded rather than propagated.

Two rules make this safe to attach arbitrary code to.

**A hook that raises does not fail the turn.** It is recorded as a
``HookFailure`` on the turn and the remaining hooks run. The alternative — one
broken accounting hook taking down an investigation that was going well — trades
a logging problem for an incident.

**A hook that raises made no decision.** A crash in ``pre_tool_use`` is read as
``Allow``, never as ``Deny``. Reading it as a denial sounds safer and is not: a
broken masking rule would silently disable every write in the system, and the
symptom would be an agent that has quietly stopped being able to do anything.

Order is explicit and then stable. Two hooks with the same order run in the
order they were registered, so a registry built the same way twice dispatches
the same way twice — which is what a trajectory comparison needs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core.agent.hooks.types import (
    ALLOW,
    Allow,
    Deny,
    HookPoint,
    HookResult,
    Rewrite,
    ToolContext,
)
from core.agent.session import Session
from core.agent.turn import HookFailure, Turn
from core.capability.result import CapabilityResult
from core.llm.types import ToolCall
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Every hook is an async callable. The registry stores them loosely and the
#: typed ``register`` overloads are where a caller's mistake is caught.
HookCallback = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RegisteredHook:
    """One callback at one point, with the order it runs in."""

    point: HookPoint
    name: str
    callback: HookCallback
    order: int = 0
    sequence: int = 0


@dataclass(slots=True)
class HookRegistry:
    """The ordered set of callbacks attached to one loop."""

    _hooks: dict[HookPoint, list[RegisteredHook]] = field(default_factory=dict, repr=False)
    _registered: int = field(default=0, repr=False)

    def register(
        self,
        point: HookPoint,
        callback: HookCallback,
        *,
        name: str = "",
        order: int = 0,
    ) -> RegisteredHook:
        """Attach ``callback`` at ``point`` and return its registration."""
        self._registered += 1
        entry = RegisteredHook(
            point=point,
            name=name or getattr(callback, "__name__", f"hook-{self._registered}"),
            callback=callback,
            order=order,
            sequence=self._registered,
        )
        self._hooks.setdefault(point, []).append(entry)
        self._hooks[point].sort(key=lambda hook: (hook.order, hook.sequence))
        return entry

    def hooks_at(self, point: HookPoint) -> tuple[RegisteredHook, ...]:
        """Return the hooks at ``point``, in the order they will run."""
        return tuple(self._hooks.get(point, ()))

    # -- observe-only points --------------------------------------------------

    async def _observe(self, point: HookPoint, *arguments: Any) -> tuple[HookFailure, ...]:
        """Run every hook at ``point``, collecting failures rather than raising."""
        failures: list[HookFailure] = []
        for hook in self.hooks_at(point):
            try:
                await hook.callback(*arguments)
            except Exception as error:  # noqa: BLE001 — a hook must never fail the turn
                failures.append(_failure(hook, error))
                logger.warning(
                    "agent.hook_failed", point=point.value, hook=hook.name, error=str(error)
                )
        return tuple(failures)

    async def run_run_start(self, session: Session) -> tuple[HookFailure, ...]:
        """Dispatch ``on_run_start``."""
        return await self._observe(HookPoint.ON_RUN_START, session)

    async def run_turn_end(self, session: Session, turn: Turn) -> tuple[HookFailure, ...]:
        """Dispatch ``on_turn_end``."""
        return await self._observe(HookPoint.ON_TURN_END, session, turn)

    async def run_run_end(self, session: Session, result: Any) -> tuple[HookFailure, ...]:
        """Dispatch ``on_run_end``."""
        return await self._observe(HookPoint.ON_RUN_END, session, result)

    async def run_cancel(self, session: Session) -> tuple[HookFailure, ...]:
        """Dispatch ``on_cancel``."""
        return await self._observe(HookPoint.ON_CANCEL, session)

    # -- the point that can change control flow -------------------------------

    async def run_pre_tool_use(
        self, call: ToolCall, context: ToolContext
    ) -> tuple[HookResult, dict[str, Any], tuple[HookFailure, ...]]:
        """Return the decision, the arguments to run with, and any hook failures.

        A denial stops the chain: once one hook has refused, running the rest
        would let a later ``Rewrite`` quietly overturn the refusal.
        """
        arguments = dict(call.arguments)
        failures: list[HookFailure] = []

        for hook in self.hooks_at(HookPoint.PRE_TOOL_USE):
            current = ToolCall(id=call.id, name=call.name, arguments=dict(arguments))
            try:
                decision = await hook.callback(current, context)
            except Exception as error:  # noqa: BLE001 — a crash is not a decision
                failures.append(_failure(hook, error))
                logger.warning(
                    "agent.hook_failed",
                    point=HookPoint.PRE_TOOL_USE.value,
                    hook=hook.name,
                    error=str(error),
                )
                continue

            if isinstance(decision, Deny):
                return decision, arguments, tuple(failures)
            if isinstance(decision, Rewrite):
                arguments = dict(decision.arguments)
                logger.info(
                    "agent.tool_arguments_rewritten",
                    hook=hook.name,
                    capability=call.name,
                    reason=decision.reason,
                )

        return ALLOW, arguments, tuple(failures)

    async def run_post_tool_use(
        self, call: ToolCall, result: CapabilityResult, context: ToolContext
    ) -> tuple[CapabilityResult, tuple[HookFailure, ...]]:
        """Return the result after filtering, and any hook failures."""
        produced = result
        failures: list[HookFailure] = []

        for hook in self.hooks_at(HookPoint.POST_TOOL_USE):
            try:
                replacement = await hook.callback(call, produced, context)
            except Exception as error:  # noqa: BLE001 — a hook must never fail the turn
                failures.append(_failure(hook, error))
                logger.warning(
                    "agent.hook_failed",
                    point=HookPoint.POST_TOOL_USE.value,
                    hook=hook.name,
                    error=str(error),
                )
                continue
            if isinstance(replacement, CapabilityResult):
                produced = replacement

        return produced, tuple(failures)


def _failure(hook: RegisteredHook, error: BaseException) -> HookFailure:
    """Return the record of one hook's exception."""
    return HookFailure(
        point=hook.point.value,
        hook=hook.name,
        error=f"{type(error).__name__}: {error}",
    )


#: A registry with nothing attached, for a loop that was given no hooks. Shared
#: because it holds no state a run could mutate.
NO_HOOKS = HookRegistry()


__all__ = [
    "NO_HOOKS",
    "Allow",
    "HookCallback",
    "HookRegistry",
    "RegisteredHook",
]
