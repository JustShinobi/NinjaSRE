"""The hooks every run gets unless somebody says otherwise.

Three, and all three observe. Tracing makes a run visible while it is
happening, accounting reports what it cost including the part nobody could
price, and the budget report says the context is filling up on the turn before
that starts costing evidence.

``model_behaviour`` is a fourth and is deliberately not among the defaults: it
needs a metric registry, and a registry is a deployment's to build. A deployment
that has one registers it beside these and gets the model family populated.

Nothing here changes control flow. The hooks that do — masking, approval
gating, guardrail rules — belong to the features that own those decisions and
register themselves; keeping the built-in set observe-only means a default
deployment has exactly one place where a call can be refused, and it is not
here.

    from core.agent.hooks import HookRegistry
    from core.agent.hooks.builtin import register_default_hooks

    hooks = HookRegistry()
    register_default_hooks(hooks)
"""

from __future__ import annotations

from core.agent.hooks.builtin import accounting, budget, model_behaviour, tracing
from core.agent.hooks.registry import HookRegistry


def register_default_hooks(hooks: HookRegistry) -> HookRegistry:
    """Attach tracing, accounting, and the budget report, and return ``hooks``.

    Ordered so a turn's log lines read in the order somebody would want them:
    what happened, what it cost, how much room is left.
    """
    tracing.register(hooks)
    accounting.register(hooks)
    budget.register(hooks)
    return hooks


def default_hooks() -> HookRegistry:
    """Return a fresh registry with the default hooks attached."""
    return register_default_hooks(HookRegistry())


__all__ = [
    "accounting",
    "budget",
    "default_hooks",
    "model_behaviour",
    "register_default_hooks",
    "tracing",
]
