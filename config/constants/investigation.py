"""Every bound the agent runs inside (Constitution Article II).

Article II is specific: *every* loop ceiling, context budget, and schema cap is
a named constant in a single owning module, and a magic number at a call site is
a defect. This module is that owner for the investigation runtime.

The values here are the starting points feature 004 tunes against the synthetic
scenario suite. Changing one is a deliberate act with a measurable effect — the
suite reports it either way (Article XII, clause 3) — which is exactly why they
are here rather than spread across the loop.
"""

from __future__ import annotations

from typing import Final

# --- The ReAct loop ----------------------------------------------------------

#: Hard iteration ceiling. The worst-case runtime bound for one investigation.
MAX_INVESTIGATION_LOOPS: Final[int] = 20

#: Iterations that may pass producing no new evidence before the loop is
#: stripped of tool access and forced to conclude in text (Article II, clause 5).
MAX_STAGNANT_ITERATIONS: Final[int] = 3

#: Concurrent tool executions in one iteration, across all parallel-safe calls.
MAX_PARALLEL_TOOL_CALLS: Final[int] = 5

# --- Capability selection ----------------------------------------------------

#: Tool schemas sent to the model in one turn, whatever the catalogue size
#: (Article II, clause 3). The cap is on the payload, not on the registry.
MAX_AGENT_TOOL_SCHEMAS: Final[int] = 40

#: Slots inside the cap reserved for cheap reasoning and knowledge capabilities,
#: so a flood of high-scoring vendor tools cannot crowd them out.
MAX_SECONDARY_FALLBACK_TOOLS: Final[int] = 5

#: Capabilities the planning stage shortlists before the loop starts.
DEFAULT_TOOL_BUDGET: Final[int] = 8

# --- Sub-agents --------------------------------------------------------------

#: Nesting depth for specialist sub-agents. A sub-agent at this depth may not
#: dispatch another one.
MAX_SUBAGENT_DEPTH: Final[int] = 2

# --- Duplicate tool-call cache ----------------------------------------------

#: Identical name-and-arguments calls are served from cache and the model is
#: told it already holds the result (Article II, clause 4). Eviction is LRU,
#: bounded by both entry count and approximate serialised size so a long run
#: cannot retain unbounded results.
INVESTIGATION_TOOL_CACHE_MAX_ENTRIES: Final[int] = 128
INVESTIGATION_TOOL_CACHE_MAX_CHARS: Final[int] = 2_000_000


__all__ = [
    "DEFAULT_TOOL_BUDGET",
    "INVESTIGATION_TOOL_CACHE_MAX_CHARS",
    "INVESTIGATION_TOOL_CACHE_MAX_ENTRIES",
    "MAX_AGENT_TOOL_SCHEMAS",
    "MAX_INVESTIGATION_LOOPS",
    "MAX_PARALLEL_TOOL_CALLS",
    "MAX_SECONDARY_FALLBACK_TOOLS",
    "MAX_STAGNANT_ITERATIONS",
    "MAX_SUBAGENT_DEPTH",
]
