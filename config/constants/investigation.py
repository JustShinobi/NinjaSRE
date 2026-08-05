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

#: Wall-clock ceiling for one run, enforced independently of the iteration
#: count. An iteration that blocks on a slow vendor consumes no iterations at
#: all, so the loop ceiling alone bounds nothing an operator can feel.
RUN_WALL_CLOCK_SECONDS: Final[float] = 1800.0

# --- Sub-agents --------------------------------------------------------------

#: Nesting depth for specialist sub-agents. A sub-agent at this depth may not
#: dispatch another one.
MAX_SUBAGENT_DEPTH: Final[int] = 2

#: Sub-agents running at once under one parent. Lower than the tool-call bound
#: because each one is a whole loop: the fan-out multiplies by its own
#: concurrent tool execution, not by one call.
MAX_PARALLEL_SUBAGENTS: Final[int] = 4

#: Share of the parent's remaining token budget one sub-agent may spend. Below
#: half, so a parent that dispatches two specialists still has budget left to
#: reason about what they found.
SUBAGENT_TOKEN_BUDGET_RATIO: Final[float] = 0.4

#: Iterations a sub-agent gets when its definition names no budget of its own.
#: A specialist that needs more than this is doing the parent's job.
DEFAULT_SUBAGENT_ITERATIONS: Final[int] = 6

# --- Context budget ----------------------------------------------------------

#: Share of the context budget evidence may occupy. The remainder holds the
#: system prompt, the tool schemas, and the conversational transcript, none of
#: which eviction can touch — evicting the schemas would leave the model unable
#: to call the tool it was about to call.
CONTEXT_EVIDENCE_BUDGET_RATIO: Final[float] = 0.6

#: An evidence entry truncated below this many characters is dropped instead.
#: A fragment too short to carry its own finding costs its full framing in the
#: prompt and tells the model nothing, which is the worst of both outcomes.
EVIDENCE_TRUNCATION_FLOOR_CHARS: Final[int] = 240

#: Value-function weights for eviction, highest-value kept. Age is the base
#: term; the rest adjust it. They are constants rather than literals in the
#: policy because the golden test pins the ordering they produce, and a
#: deliberate retune should show up as a diff here and a diff in that test.
EVIDENCE_VALUE_RECENCY_WEIGHT: Final[float] = 1.0
EVIDENCE_VALUE_CITED_BONUS: Final[float] = 2.0
EVIDENCE_VALUE_SIZE_PENALTY: Final[float] = 0.5
EVIDENCE_VALUE_UNRELIABLE_PENALTY: Final[float] = 0.75

#: Utilisation at which the budget hook starts warning. Below 1.0 on purpose:
#: by the time eviction is happening the run has already lost evidence, and the
#: useful moment to say so is the turn before that.
CONTEXT_BUDGET_WARNING_RATIO: Final[float] = 0.9

#: Sources whose entries carry the reliability penalty above. Reasoning output
#: is the agent's own prose: worth keeping while it is fresh, first to go when
#: something measured is competing for the same tokens.
UNRELIABLE_EVIDENCE_SOURCES: Final[tuple[str, ...]] = ("reasoning",)

# --- Mid-run interaction -----------------------------------------------------

#: How long queued user input is held before it is merged into the next turn.
#: Someone typing three sentences in three messages meant one instruction, and
#: merging them at the boundary keeps it that way.
MESSAGE_QUEUE_DEBOUNCE_MS: Final[int] = 1500

#: How long a question put to a human stays open. On expiry the handoff
#: resolves to a refusal, never to a guess: an agent that invents the answer to
#: the question it needed a human for has learned to skip asking.
HANDOFF_TIMEOUT_SECONDS: Final[float] = 900.0

# --- Intake ------------------------------------------------------------------

#: Confidence at or above which intake's "this is not an incident" verdict ends
#: the run before a single capability executes. A threshold rather than a
#: boolean because the cost of the two mistakes is not symmetric: dropping a
#: real incident is an outage nobody looked at, and investigating a greeting is
#: one wasted model call. It is tuned against the synthetic corpus, which is why
#: it is here and not at the call site.
NOISE_CLASSIFICATION_THRESHOLD: Final[float] = 0.7

#: How far before the alert fired the incident window starts. The interesting
#: change almost never happens at the instant the threshold was crossed — it
#: happens during the deploy or the traffic shift that preceded it.
INCIDENT_WINDOW_LEAD_MINUTES: Final[int] = 15

#: The span used when nothing in the alert says when the incident began. Wide
#: enough to contain a deploy and narrow enough that a log query over it still
#: returns something an operator can read.
DEFAULT_INCIDENT_WINDOW_MINUTES: Final[int] = 60

#: Confidence recorded for a window derived from timestamps the alert carried.
DERIVED_WINDOW_CONFIDENCE: Final[float] = 0.9

#: Confidence recorded for the defaulted span above. Deliberately low: every
#: time-bounded call downstream is bounded by a guess, and the trace has to say
#: so rather than presenting it as a measurement.
FALLBACK_WINDOW_CONFIDENCE: Final[float] = 0.2

#: How far back deduplication looks for an incident this alert belongs to.
#: An alert storm is the normal case in production, and re-investigating the
#: sixth copy costs a full run to reach the conclusion the first one reached.
DEDUPLICATION_WINDOW_MINUTES: Final[int] = 30

# --- Planning ----------------------------------------------------------------

#: Score below which a planned action is recorded but not treated as binding.
#: The plan is advisory by design, and a shortlist assembled from weak matches
#: is worse than no shortlist: it would hold the loop to capabilities that
#: scored well only because nothing else did.
PLAN_CONFIDENCE_FLOOR: Final[float] = 1.0

# --- What a run carries about its incident -----------------------------------

#: Keys on a run's context. Named because three parties read them — the model,
#: the incident-window guard, and the evaluation suite — and a key spelled two
#: ways is a context entry two of the three never find.
CONTEXT_ALERT_NAME: Final[str] = "alert_name"
CONTEXT_ALERT_SOURCE: Final[str] = "alert_source"
CONTEXT_SEVERITY: Final[str] = "severity"
CONTEXT_COMPONENTS: Final[str] = "components"
CONTEXT_WINDOW_START: Final[str] = "incident_window_start"
CONTEXT_WINDOW_END: Final[str] = "incident_window_end"
CONTEXT_WINDOW_CONFIDENCE: Final[str] = "incident_window_confidence"
CONTEXT_PLAN: Final[str] = "planned_capabilities"
CONTEXT_PLAN_RATIONALE: Final[str] = "plan_rationale"

# --- Incident-window enforcement ---------------------------------------------

#: Argument names a time-bounded capability uses for the two ends of its range.
#: Enforcement is by name because the alternative — a per-capability
#: declaration — would be unenforced for every capability whose author forgot,
#: which is exactly the set that needs it.
TIME_WINDOW_START_ARGUMENTS: Final[tuple[str, ...]] = (
    "start",
    "start_at",
    "start_time",
    "since",
    "from_time",
)
TIME_WINDOW_END_ARGUMENTS: Final[tuple[str, ...]] = (
    "end",
    "end_at",
    "end_time",
    "until",
    "to_time",
)

# --- Diagnosis ---------------------------------------------------------------

#: Schema caps on the structured diagnosis (Article II, clause 3). A model asked
#: for an unbounded list produces one, and a causal chain of forty steps is not
#: a causal chain — it is a transcript with numbers on it.
MAX_DIAGNOSIS_CLAIMS: Final[int] = 12
MAX_CAUSAL_CHAIN_STEPS: Final[int] = 8
MAX_REMEDIATION_STEPS: Final[int] = 8

#: Evidence entries offered to the diagnosis call. The call sees the conclusion
#: and the evidence and nothing else, so this is the whole of its context
#: budget; entries beyond it are dropped most-recent-first.
MAX_DIAGNOSIS_EVIDENCE_ENTRIES: Final[int] = 40

# --- Which runtime is in use -------------------------------------------------

#: Selects the runtime. Anything but the canonical one is experimental, and the
#: guard in front of the evaluation suite refuses to publish a number produced
#: by one (Article V).
NINJASRE_RUNTIME_ENV: Final[str] = "NINJASRE_RUNTIME"

#: The first-party ReAct loop. The only runtime a benchmark may use.
RUNTIME_CANONICAL: Final[str] = "canonical"

#: The experimental adapter over a vendor agent SDK. Never the default; it
#: exists so a team already invested in that SDK has a migration path, and it
#: documents the guardrails it cannot enforce.
RUNTIME_CLAUDE_SDK: Final[str] = "claude_sdk"

SUPPORTED_RUNTIMES: Final[tuple[str, ...]] = (RUNTIME_CANONICAL, RUNTIME_CLAUDE_SDK)
DEFAULT_RUNTIME: Final[str] = RUNTIME_CANONICAL

# --- Transcript compaction ---------------------------------------------------

#: Transcript length at which compaction runs. Below this a long conversation
#: is cheaper to keep than to summarise, and a summary the model has to read
#: alongside the messages it summarises costs more than either.
TRANSCRIPT_COMPACTION_TRIGGER_MESSAGES: Final[int] = 40

#: Messages kept verbatim after compaction, counting back from the most recent.
#: The recent turns are where the model's current line of reasoning lives, and
#: summarising those is how a run loses the thread it was following.
TRANSCRIPT_COMPACTION_KEEP_MESSAGES: Final[int] = 12

# --- Duplicate tool-call cache ----------------------------------------------

#: Identical name-and-arguments calls are served from cache and the model is
#: told it already holds the result (Article II, clause 4). Eviction is LRU,
#: bounded by both entry count and approximate serialised size so a long run
#: cannot retain unbounded results.
INVESTIGATION_TOOL_CACHE_MAX_ENTRIES: Final[int] = 128
INVESTIGATION_TOOL_CACHE_MAX_CHARS: Final[int] = 2_000_000


__all__ = [
    "CONTEXT_ALERT_NAME",
    "CONTEXT_ALERT_SOURCE",
    "CONTEXT_BUDGET_WARNING_RATIO",
    "CONTEXT_COMPONENTS",
    "CONTEXT_EVIDENCE_BUDGET_RATIO",
    "CONTEXT_PLAN",
    "CONTEXT_PLAN_RATIONALE",
    "CONTEXT_SEVERITY",
    "CONTEXT_WINDOW_CONFIDENCE",
    "CONTEXT_WINDOW_END",
    "CONTEXT_WINDOW_START",
    "DEDUPLICATION_WINDOW_MINUTES",
    "DEFAULT_INCIDENT_WINDOW_MINUTES",
    "DEFAULT_RUNTIME",
    "DEFAULT_SUBAGENT_ITERATIONS",
    "DEFAULT_TOOL_BUDGET",
    "DERIVED_WINDOW_CONFIDENCE",
    "EVIDENCE_TRUNCATION_FLOOR_CHARS",
    "EVIDENCE_VALUE_CITED_BONUS",
    "EVIDENCE_VALUE_RECENCY_WEIGHT",
    "EVIDENCE_VALUE_SIZE_PENALTY",
    "EVIDENCE_VALUE_UNRELIABLE_PENALTY",
    "FALLBACK_WINDOW_CONFIDENCE",
    "HANDOFF_TIMEOUT_SECONDS",
    "INCIDENT_WINDOW_LEAD_MINUTES",
    "INVESTIGATION_TOOL_CACHE_MAX_CHARS",
    "INVESTIGATION_TOOL_CACHE_MAX_ENTRIES",
    "MAX_AGENT_TOOL_SCHEMAS",
    "MAX_CAUSAL_CHAIN_STEPS",
    "MAX_DIAGNOSIS_CLAIMS",
    "MAX_DIAGNOSIS_EVIDENCE_ENTRIES",
    "MAX_INVESTIGATION_LOOPS",
    "MAX_PARALLEL_SUBAGENTS",
    "MAX_PARALLEL_TOOL_CALLS",
    "MAX_REMEDIATION_STEPS",
    "MAX_SECONDARY_FALLBACK_TOOLS",
    "MAX_STAGNANT_ITERATIONS",
    "MAX_SUBAGENT_DEPTH",
    "MESSAGE_QUEUE_DEBOUNCE_MS",
    "NINJASRE_RUNTIME_ENV",
    "NOISE_CLASSIFICATION_THRESHOLD",
    "PLAN_CONFIDENCE_FLOOR",
    "RUNTIME_CANONICAL",
    "RUNTIME_CLAUDE_SDK",
    "RUN_WALL_CLOCK_SECONDS",
    "SUBAGENT_TOKEN_BUDGET_RATIO",
    "SUPPORTED_RUNTIMES",
    "TIME_WINDOW_END_ARGUMENTS",
    "TIME_WINDOW_START_ARGUMENTS",
    "UNRELIABLE_EVIDENCE_SOURCES",
]
