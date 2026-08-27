# Feature 004 — Agent Runtime

- **Wave:** 0 — Foundation
- **Branch:** `feat/004-agent-runtime`
- **Status:** Draft
- **Depends on:** 001, 002, 003
- **Blocks:** 005, 010, 017, 018, 020, 028
- **ADRs:** [0003](../../docs/adr/0003-single-canonical-runtime.md)

## Summary

The canonical ReAct loop: the single runtime whose behaviour defines correctness.
It absorbs the capabilities that made the Claude Agent SDK attractive — specialist
sub-agents, parallel execution, mid-run message queue, lifecycle hooks, human
handoff — while keeping every guardrail inside a loop we control, so trajectory
evaluation is meaningful and no LLM vendor is load-bearing.

## User scenarios

### Primary story

An engineer starts an investigation. The agent gathers evidence, dispatches a
specialist sub-agent to analyse logs in isolation, receives a structured finding
back, and concludes — all within a bounded number of iterations, a bounded context
budget, and a bounded schema payload, with every step visible in the trace.

### Acceptance scenarios

1. **Given** an incident and a resolved catalogue, **when** the loop runs, **then**
   it never exceeds `MAX_INVESTIGATION_LOOPS` iterations.
2. **Given** the model requests a tool call identical to a previous one, **when**
   the loop processes it, **then** the cached result is returned and the model is
   told explicitly it already has that result.
3. **Given** an iteration where every requested call was a replayed duplicate,
   **when** it completes, **then** a stagnation nudge is appended; after
   `MAX_STAGNANT_ITERATIONS` such iterations, tool access is stripped and the model
   gets one final text-only turn.
4. **Given** accumulated evidence approaching the model's context limit, **when**
   the next turn is prepared, **then** the lowest-value evidence is evicted or
   truncated per the budget policy, and the eviction is recorded.
5. **Given** a set of `parallel_safe` tool calls, **when** the model requests them
   together, **then** they execute concurrently up to `MAX_PARALLEL_TOOL_CALLS`,
   and non-parallel-safe calls serialise.
6. **Given** a task suited to a specialist, **when** the loop dispatches a
   sub-agent, **then** the sub-agent runs in an isolated context with its own
   capability subset and budget, and returns a **structured finding**, not a
   transcript.
7. **Given** an investigation in progress, **when** a user submits additional
   context, **then** it is queued, debounced, and merged into the next turn
   boundary as a single numbered guidance block, and a `message_queued` event is
   emitted.
8. **Given** a capability whose `side_effect_level` requires approval, **when** the
   model requests it, **then** the loop suspends, emits an approval request, and
   resumes or aborts on the human decision.
9. **Given** the model needs information only a human has, **when** it invokes the
   handoff capability, **then** a question is surfaced at the active surface and
   the loop waits under a configured timeout.
10. **Given** an LLM invoke failure mid-loop, **when** it occurs, **then** the loop
    degrades to a partial result preserving gathered evidence; it does not crash.
11. **Given** a turn completes, **when** lifecycle hooks fire, **then** hooks run
    in declared order and a hook failure is recorded without failing the turn.
12. **Given** the user cancels, **when** cancellation is signalled, **then** the
    loop stops at the next safe point, in-flight calls are reaped, and session
    state remains consistent.

### Edge cases

- Sub-agent requesting another sub-agent beyond `MAX_SUBAGENT_DEPTH`.
- A parallel batch where one call fails and others succeed.
- Context budget so tight that even the system prompt plus one evidence entry
  exceeds it.
- The model emitting a tool call for a capability not in the sent schema set.
- Cancellation arriving while a sub-agent is mid-flight.
- A queued message arriving during the final turn after tool access was stripped.
- An approval that times out while the rest of the batch has already executed.

## Requirements

### Functional

**Loop core**

- **FR-001** The loop MUST implement think → select → execute → observe with a
  hard iteration ceiling `MAX_INVESTIGATION_LOOPS`.
- **FR-002** Before the first model turn, deterministic **seed calls** MAY execute
  for the incident's source, so the loop starts with evidence already gathered.
- **FR-003** Identical tool name + arguments MUST be served from an in-run cache,
  and the model MUST be told explicitly that the result is a replay.
- **FR-004** An iteration in which no fresh evidence was produced MUST increment a
  stagnation counter and append a nudge. At `MAX_STAGNANT_ITERATIONS`, tool access
  MUST be stripped for one final text-only turn.
- **FR-005** Context budget MUST be enforced before every model call, evicting or
  truncating the lowest-value evidence per a documented policy, recording every
  eviction.
- **FR-006** Conclusion acceptance MUST be pluggable: the default accepts a
  text-only answer; a stricter policy MAY refuse an early stop until planned
  capabilities have been called.
- **FR-007** An LLM invoke failure MUST produce a degraded partial result
  preserving evidence (FR-010 acceptance), never an unhandled exception.
- **FR-008** Every iteration MUST emit a trace record: selected capabilities,
  rationale, model call, tool results, budget actions, guardrail actions.

**Sub-agents**

- **FR-009** The runtime MUST support specialist sub-agents, each with an isolated
  context window, a capability subset, its own iteration and token budget, and a
  declared structured return type.
- **FR-010** A sub-agent MUST return a structured finding, not a raw transcript.
  The parent receives the finding as evidence.
- **FR-011** Sub-agent nesting MUST be bounded by `MAX_SUBAGENT_DEPTH`.
- **FR-012** Sub-agents MAY run concurrently, bounded by a configured fan-out
  limit; a failed sub-agent MUST NOT fail the parent.
- **FR-013** Sub-agent definitions MUST be declarative and configurable per team
  (feature 013), not hard-coded.

**Concurrency and interaction**

- **FR-014** Tool calls declared `parallel_safe` MUST execute concurrently up to
  `MAX_PARALLEL_TOOL_CALLS`; others serialise. Partial batch failure MUST be
  handled per-call.
- **FR-015** A mid-run message queue MUST accept user input during a run, debounce
  it, and merge it at the next turn boundary as one numbered guidance block.
- **FR-016** Cancellation MUST stop the loop at the next safe point, reap in-flight
  work, and leave session state consistent and resumable.
- **FR-017** A human-handoff capability MUST let the agent ask a question at the
  active surface, with a configured timeout and a default-deny outcome on expiry.

**Hooks and integration points**

- **FR-018** Lifecycle hooks MUST exist at: `on_run_start`, `pre_tool_use`,
  `post_tool_use`, `on_turn_end`, `on_run_end`, `on_cancel`.
- **FR-019** Hooks MUST run in declared order. A hook failure MUST be recorded and
  MUST NOT fail the turn.
- **FR-020** `pre_tool_use` MUST be able to **deny** a call (used by guardrails and
  approvals). Denial MUST be returned to the model as a structured result.

**Runtime port**

- **FR-021** A `Runtime` protocol MUST define the contract. The first-party loop is
  the canonical implementation.
- **FR-022** An experimental `ClaudeAgentSdkRuntime` adapter MAY implement the
  port. It MUST NOT be the default, MUST be marked experimental, and MUST document
  which guardrails it cannot enforce.
- **FR-023** A guard MUST fail any evaluation or benchmark invocation that uses a
  non-canonical runtime.

**Sessions**

- **FR-024** Sessions MUST be persistable and resumable, carrying transcript,
  evidence, and accounting.
- **FR-025** Transcript compaction MUST be supported for long sessions, preserving
  evidence references while summarising conversational turns.

### Key entities

| Entity | Description |
|---|---|
| **Runtime** | The protocol; the canonical loop is its reference implementation |
| **Session** | Persistent conversation state: transcript, evidence, accounting, status |
| **Turn** | One model call plus the tool executions it triggered |
| **Iteration** | One pass of the loop; a turn plus budget and guardrail processing |
| **SubAgent** | A declarative specialist definition with capability subset, budget, and return schema |
| **Finding** | The structured result a sub-agent returns to its parent |
| **ToolCallCache** | In-run deduplication keyed on name + normalised arguments |
| **ContextBudget** | Policy governing what is kept, truncated, or evicted before each call |
| **Hook** | A registered callback at a lifecycle point, able to observe and (for `pre_tool_use`) deny |

## Success criteria

- **SC-001** A pathological scenario designed to loop forever terminates within
  `MAX_INVESTIGATION_LOOPS` on all nine providers.
- **SC-002** The stagnation breaker fires deterministically in a fixture designed
  to induce duplicate-only iterations.
- **SC-003** With a context budget of 8k tokens and 200 evidence entries, the loop
  completes and the eviction log explains every drop.
- **SC-004** A sub-agent's context never contains the parent's transcript —
  asserted by a test inspecting the sub-agent's prompt.
- **SC-005** Parallel execution of 10 `parallel_safe` calls completes in under 2×
  the slowest single call.
- **SC-006** Cancellation mid-sub-agent leaves a resumable session; resuming
  produces a coherent continuation.
- **SC-007** A benchmark invoked with the SDK adapter fails the guard (FR-023).
- **SC-008** Trace records are sufficient to replay a full run offline.

## Out of scope

- The six-stage pipeline that wraps the loop (feature 005)
- Approval decision workflow and rollback (feature 017)
- Surface rendering of questions and approvals (features 018–023)
- Memory hook implementations (feature 010)

## Clarifications

| Question | Resolution |
|---|---|
| Why implement sub-agents rather than adopt the SDK's? | ADR 0003. Guardrails, provider neutrality, and trajectory evaluation all require the loop to be ours. Sub-agents are the largest single capability the SDK provided and are ~1k LOC here. |
| Do sub-agents share the parent's tool call cache? | No. Cache is per-loop. A sub-agent re-fetching evidence the parent already has is a scoring signal worth seeing, not a bug to hide. |
| What is "lowest-value evidence" for eviction? | Age, size, source reliability, and whether it was cited in a prior turn — the policy is documented in `core/agent/context_budget.py` and covered by a golden test. |
| Can a hook mutate the model request? | `pre_tool_use` may deny and may rewrite arguments (masking does exactly this). It may not inject new tool calls. |
