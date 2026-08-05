"""Alternative runtimes, all of them experimental by construction.

Anything in this package answers ``False`` to ``Runtime.is_canonical``, and
``core.agent.guard`` reads that property in front of every evaluation and
benchmark entry point. The port exists so a team can migrate from a vendor
agent SDK without a rewrite; it exists in Wave 0 specifically so no adapter can
ever become load-bearing (ADR 0003).

Each adapter documents the guardrails it cannot enforce, as a module docstring
for a reader and as ``UNENFORCEABLE_GUARDRAILS`` for a console.
"""

from __future__ import annotations

from core.agent.adapters.claude_sdk import (
    UNENFORCEABLE_GUARDRAILS,
    ClaudeAgentSdkRuntime,
    ExperimentalRuntimeError,
)

__all__ = [
    "UNENFORCEABLE_GUARDRAILS",
    "ClaudeAgentSdkRuntime",
    "ExperimentalRuntimeError",
]
