"""Where guardrails, masking, approvals, and memory attach to the loop.

The loop knows nothing about any of them. It knows six points and three
results, and every feature that needs to see or change a run registers a
callback rather than editing ``react_loop``. That is what makes the effect of a
learning mechanism ablatable: unregister the hook and measure the difference
(Article VII).

    from core.agent.hooks import HookPoint, HookRegistry, Deny

    hooks = HookRegistry()
    hooks.register(HookPoint.PRE_TOOL_USE, require_approval, name="approvals", order=10)
"""

from __future__ import annotations

from core.agent.hooks.registry import (
    NO_HOOKS,
    HookCallback,
    HookRegistry,
    RegisteredHook,
)
from core.agent.hooks.types import (
    ALLOW,
    Allow,
    CancelHook,
    Deny,
    HookPoint,
    HookResult,
    PostToolUseHook,
    PreToolUseHook,
    Rewrite,
    RunEndHook,
    RunStartHook,
    ToolContext,
    TurnEndHook,
)

__all__ = [
    "ALLOW",
    "NO_HOOKS",
    "Allow",
    "CancelHook",
    "Deny",
    "HookCallback",
    "HookPoint",
    "HookRegistry",
    "HookResult",
    "PostToolUseHook",
    "PreToolUseHook",
    "RegisteredHook",
    "Rewrite",
    "RunEndHook",
    "RunStartHook",
    "ToolContext",
    "TurnEndHook",
]
