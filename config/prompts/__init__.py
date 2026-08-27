"""Prompt text, as constants.

Prompts live in tier 4 so any tier may read one without creating a cycle: the
investigation stages in ``core/``, the specialist sub-agents, the diagnosis
formatter in ``platform/reporting/``, and the console's preview all reach the
same string.

Convention
----------

One module per prompt domain, named for what it prompts about — ``intake.py``,
``diagnosis.py``, ``memory_recall.py`` — and re-exported here the way
``config.constants`` re-exports its domains.

Within a module:

- A prompt is an ``UPPER_SNAKE_CASE`` ``Final[str]`` module-level constant.
  Text that varies at runtime is a ``str.format`` template with named fields,
  never an f-string built at the call site, so the same text can be read,
  diffed, reviewed, and version-controlled as one artefact.
- Each constant carries a comment naming which stage or sub-agent sends it, and
  the structured output it expects back if any.
- A prompt that asks for structured output names the schema it is paired with.
  The two change together or the change is wrong.

Rules
-----

- **English only** (Constitution Article XIII). A prompt is source.
- **No secrets, no identifiers.** Prompts are templates, not data. Values are
  substituted by the caller, and everything bound for an external provider
  passes through the masking layer first (Article IV, clause 5).
- **No behaviour here.** Selection, composition, and budget-aware truncation
  belong to the module that sends the prompt. This package only holds text.
- Prompts are gated changes: editing one goes through the approval workflow in
  feature 015, which is why they are constants in a reviewable file rather than
  rows in a database.
"""

from __future__ import annotations

from config.prompts.investigation import (
    DEFAULT_RUNTIME_SYSTEM_PROMPT,
    DEGRADED_EVIDENCE_LINE,
    DEGRADED_INVESTIGATION_PREAMBLE,
    DUPLICATE_TOOL_CALL_REPLAY,
    FINAL_TURN_WITHOUT_TOOLS,
    HANDOFF_TIMED_OUT,
    INVESTIGATION_SYSTEM_PROMPT,
    QUEUED_GUIDANCE_BLOCK,
    STAGNATION_NUDGE,
    SUBAGENT_DEPTH_REFUSED,
    SUBAGENT_FINDING_SUMMARY,
    SUBAGENT_SYSTEM_PROMPT,
    SUBAGENT_UNKNOWN,
    SUBJECT_BRIEF_HEADING,
)
from config.prompts.knowledge import (
    KNOWLEDGE_CHUNK,
    KNOWLEDGE_DISABLED,
    KNOWLEDGE_EMPTY,
    KNOWLEDGE_GUIDANCE,
    KNOWLEDGE_HEADER,
    KNOWLEDGE_UNCONFIGURED,
    PROPOSAL_ATTRIBUTION,
    PROPOSAL_QUEUED,
    PROPOSAL_REFUSED,
    PROPOSAL_UNCONFIGURED,
    TOPOLOGY_DISABLED,
    TOPOLOGY_EDGE,
    TOPOLOGY_EDGE_STALE,
    TOPOLOGY_EMPTY,
    TOPOLOGY_GUIDANCE,
    TOPOLOGY_HEADER,
    TOPOLOGY_TRUNCATED,
    TOPOLOGY_UNAVAILABLE,
    TOPOLOGY_UNCONFIGURED,
)
from config.prompts.memory import (
    EPISODE_EXTRACTION_FAILED,
    EPISODE_EXTRACTION_REQUEST,
    EPISODE_EXTRACTION_SYSTEM_PROMPT,
    EPISODE_SKIPPED_DISABLED,
    EPISODE_SKIPPED_TOO_SHORT,
    MEMORY_RECALL_DISABLED,
    MEMORY_RECALL_EMPTY,
    MEMORY_RECALL_EPISODE,
    MEMORY_RECALL_GUIDANCE,
    MEMORY_RECALL_HEADER,
    MEMORY_UNCONFIGURED,
)
from config.prompts.resilience import (
    CALL_BUDGET_EXCEEDED,
    MISSING_ARGUMENT_CORRECTION,
    NO_CALL_CORRECTION,
    REPAIR_BUDGET_EXHAUSTED,
    REPETITION_BREAK,
    REPETITION_UNBROKEN,
    UNKNOWN_ARGUMENT_CORRECTION,
    UNREADABLE_CALL_CORRECTION,
)
from config.prompts.strategy import (
    STRATEGY_BELOW_THRESHOLD,
    STRATEGY_DISABLED,
    STRATEGY_NO_RESOLVED_EPISODES,
    STRATEGY_NO_UNRESOLVED_EPISODES,
    STRATEGY_PROMPT_VERSION,
    STRATEGY_RECALL_HEADER,
    STRATEGY_RECALL_OPERATOR_EDITS,
    STRATEGY_RECALL_SECTION,
    STRATEGY_SECTION_TITLES,
    STRATEGY_SYNTHESIS_EPISODE,
    STRATEGY_SYNTHESIS_FAILED,
    STRATEGY_SYNTHESIS_REQUEST,
    STRATEGY_SYNTHESIS_SYSTEM_PROMPT,
)

__all__ = [
    "CALL_BUDGET_EXCEEDED",
    "DEFAULT_RUNTIME_SYSTEM_PROMPT",
    "INVESTIGATION_SYSTEM_PROMPT",
    "DEGRADED_EVIDENCE_LINE",
    "DEGRADED_INVESTIGATION_PREAMBLE",
    "DUPLICATE_TOOL_CALL_REPLAY",
    "EPISODE_EXTRACTION_FAILED",
    "EPISODE_EXTRACTION_REQUEST",
    "EPISODE_EXTRACTION_SYSTEM_PROMPT",
    "EPISODE_SKIPPED_DISABLED",
    "EPISODE_SKIPPED_TOO_SHORT",
    "FINAL_TURN_WITHOUT_TOOLS",
    "HANDOFF_TIMED_OUT",
    "KNOWLEDGE_CHUNK",
    "KNOWLEDGE_DISABLED",
    "KNOWLEDGE_EMPTY",
    "KNOWLEDGE_GUIDANCE",
    "KNOWLEDGE_HEADER",
    "KNOWLEDGE_UNCONFIGURED",
    "MEMORY_RECALL_DISABLED",
    "MEMORY_RECALL_EMPTY",
    "MEMORY_RECALL_EPISODE",
    "MEMORY_RECALL_GUIDANCE",
    "MEMORY_RECALL_HEADER",
    "MEMORY_UNCONFIGURED",
    "MISSING_ARGUMENT_CORRECTION",
    "NO_CALL_CORRECTION",
    "PROPOSAL_ATTRIBUTION",
    "PROPOSAL_QUEUED",
    "PROPOSAL_REFUSED",
    "PROPOSAL_UNCONFIGURED",
    "QUEUED_GUIDANCE_BLOCK",
    "REPAIR_BUDGET_EXHAUSTED",
    "REPETITION_BREAK",
    "REPETITION_UNBROKEN",
    "STAGNATION_NUDGE",
    "SUBJECT_BRIEF_HEADING",
    "STRATEGY_BELOW_THRESHOLD",
    "STRATEGY_DISABLED",
    "STRATEGY_NO_RESOLVED_EPISODES",
    "STRATEGY_NO_UNRESOLVED_EPISODES",
    "STRATEGY_PROMPT_VERSION",
    "STRATEGY_RECALL_HEADER",
    "STRATEGY_RECALL_OPERATOR_EDITS",
    "STRATEGY_RECALL_SECTION",
    "STRATEGY_SECTION_TITLES",
    "STRATEGY_SYNTHESIS_EPISODE",
    "STRATEGY_SYNTHESIS_FAILED",
    "STRATEGY_SYNTHESIS_REQUEST",
    "STRATEGY_SYNTHESIS_SYSTEM_PROMPT",
    "SUBAGENT_DEPTH_REFUSED",
    "SUBAGENT_FINDING_SUMMARY",
    "SUBAGENT_SYSTEM_PROMPT",
    "SUBAGENT_UNKNOWN",
    "TOPOLOGY_DISABLED",
    "TOPOLOGY_EDGE",
    "TOPOLOGY_EDGE_STALE",
    "TOPOLOGY_EMPTY",
    "TOPOLOGY_GUIDANCE",
    "TOPOLOGY_HEADER",
    "TOPOLOGY_TRUNCATED",
    "TOPOLOGY_UNAVAILABLE",
    "TOPOLOGY_UNCONFIGURED",
    "UNKNOWN_ARGUMENT_CORRECTION",
    "UNREADABLE_CALL_CORRECTION",
]
