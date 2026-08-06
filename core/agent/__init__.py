"""The canonical ReAct loop and everything that bounds it.

This is the runtime whose behaviour defines correctness. Every guardrail
Article II names lives inside its control flow — the iteration ceiling, the
duplicate-call cache, the stagnation breaker, the context budget — because a
guardrail is a property of the loop and there is no seam to insert one into a
loop somebody else owns.

The public surface is the port and the loop that implements it::

    from core.agent import ReActLoop, RunRequest

    loop = ReActLoop(llm=get_llm(role="investigator"), tools=selected)
    result = await loop.run(RunRequest(objective="Why is checkout failing?"))

Everything else — the cache, the budget policy, the hook registry, the
sub-agent dispatcher, the message queue — is reached through that loop and is
nobody else's import.
"""

from __future__ import annotations

from core.agent.compaction import CompactionResult, apply_compaction, compact
from core.agent.conclusion import (
    Acceptance,
    AcceptAnyAnswer,
    ConclusionPolicy,
    RequirePlannedCapabilities,
)
from core.agent.context_budget import BudgetPolicy, apply_budget, evidence_value
from core.agent.degradation import degraded_answer, degraded_result
from core.agent.handoff import (
    HandoffAnswer,
    HandoffChannel,
    HandoffQuestion,
    HumanHandoff,
    NoHumanAvailable,
    SecretRequestRefused,
    ask_human,
    with_escalation,
)
from core.agent.hooks import (
    ALLOW,
    NO_HOOKS,
    Allow,
    Deny,
    HookPoint,
    HookRegistry,
    HookResult,
    Rewrite,
    ToolContext,
)
from core.agent.interaction import (
    Answer,
    ApprovalInteraction,
    Attention,
    AttentionState,
    Interaction,
    InteractionClosure,
    InteractionEvent,
    InteractionKind,
    InteractionRegistry,
    InteractionState,
    InteractionSurface,
    ProgressNotifier,
    ProgressReport,
    ProgressSink,
    Question,
    Resolution,
    attention_of,
)
from core.agent.message_queue import MergeReceipt, MessageQueue, QueuedMessage, ReceiptSink
from core.agent.react_loop import CANONICAL_RUNTIME_NAME, PAUSED_ANSWER, ReActLoop
from core.agent.runtime_port import RunRequest, RunResult, RunStatus, Runtime, SeedCall
from core.agent.seed_calls import EMPTY_SEED_CATALOGUE, SeedCatalogue, SeedPlan
from core.agent.session import EvidenceEntry, Session, SessionStatus
from core.agent.store import InMemorySessionStore, SessionStore
from core.agent.subagents import (
    DEFAULT_SUBAGENTS,
    Finding,
    StaticSubAgents,
    SubAgent,
    SubAgentSource,
)
from core.agent.tool_cache import ToolCallCache
from core.agent.turn import (
    BudgetAction,
    BudgetActionKind,
    GuardrailAction,
    GuardrailActionKind,
    HookFailure,
    ToolExecution,
    Turn,
)

__all__ = [
    "ALLOW",
    "CANONICAL_RUNTIME_NAME",
    "DEFAULT_SUBAGENTS",
    "EMPTY_SEED_CATALOGUE",
    "NO_HOOKS",
    "PAUSED_ANSWER",
    "AcceptAnyAnswer",
    "Acceptance",
    "Allow",
    "Answer",
    "ApprovalInteraction",
    "Attention",
    "AttentionState",
    "BudgetAction",
    "BudgetActionKind",
    "BudgetPolicy",
    "CompactionResult",
    "ConclusionPolicy",
    "Deny",
    "EvidenceEntry",
    "Finding",
    "GuardrailAction",
    "GuardrailActionKind",
    "HandoffAnswer",
    "HandoffChannel",
    "HandoffQuestion",
    "HookFailure",
    "HookPoint",
    "HookRegistry",
    "HookResult",
    "HumanHandoff",
    "InMemorySessionStore",
    "Interaction",
    "InteractionClosure",
    "InteractionEvent",
    "InteractionKind",
    "InteractionRegistry",
    "InteractionState",
    "InteractionSurface",
    "MergeReceipt",
    "MessageQueue",
    "NoHumanAvailable",
    "ProgressNotifier",
    "ProgressReport",
    "ProgressSink",
    "Question",
    "QueuedMessage",
    "ReActLoop",
    "ReceiptSink",
    "RequirePlannedCapabilities",
    "Resolution",
    "Rewrite",
    "RunRequest",
    "RunResult",
    "RunStatus",
    "Runtime",
    "SecretRequestRefused",
    "SeedCall",
    "SeedCatalogue",
    "SeedPlan",
    "Session",
    "SessionStatus",
    "SessionStore",
    "StaticSubAgents",
    "SubAgent",
    "SubAgentSource",
    "ToolCallCache",
    "ToolContext",
    "ToolExecution",
    "Turn",
    "apply_budget",
    "apply_compaction",
    "ask_human",
    "attention_of",
    "compact",
    "degraded_answer",
    "degraded_result",
    "evidence_value",
    "with_escalation",
]
