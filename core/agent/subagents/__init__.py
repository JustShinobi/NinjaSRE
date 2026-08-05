"""Specialists: an isolated context, a capability subset, and a finding back.

This is the largest capability the Claude Agent SDK provided and the reason
ADR 0003 had to argue rather than assert. Building it costs about a thousand
lines; adopting it would have cost the guardrails, provider neutrality, and
reproducible trajectories, which are three constitutional requirements.

The shape is small on purpose. A specialist is a declaration, a dispatch is a
tool call the loop intercepts, and what comes back is a ``Finding`` — never a
transcript, because the parent's context is exactly what the isolation was
protecting.

    from core.agent.subagents import DEFAULT_SUBAGENTS, SubAgent

    loop = ReActLoop(llm=client, tools=selected, subagents=DEFAULT_SUBAGENTS)
"""

from __future__ import annotations

from core.agent.subagents.definition import (
    DEFAULT_SUBAGENTS,
    StaticSubAgents,
    SubAgent,
    SubAgentSource,
    default_subagent_source,
)
from core.agent.subagents.dispatch import (
    DISPATCH_CAPABILITY,
    SubAgentCatalogue,
    SubAgentDispatcher,
    SubAgentRun,
    SubAgentRunner,
    child_budget,
    dispatch_schema,
)
from core.agent.subagents.findings import (
    FINDING_SCHEMA,
    Finding,
    FindingEvidence,
    failed_finding,
    finding_from_answer,
    finding_from_structured,
)

__all__ = [
    "DEFAULT_SUBAGENTS",
    "DISPATCH_CAPABILITY",
    "FINDING_SCHEMA",
    "Finding",
    "FindingEvidence",
    "StaticSubAgents",
    "SubAgent",
    "SubAgentCatalogue",
    "SubAgentDispatcher",
    "SubAgentRun",
    "SubAgentRunner",
    "SubAgentSource",
    "child_budget",
    "default_subagent_source",
    "dispatch_schema",
    "failed_finding",
    "finding_from_answer",
    "finding_from_structured",
]
