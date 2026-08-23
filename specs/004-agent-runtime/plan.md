# Plan — 004 Agent Runtime

## Summary

Port Tracer's bounded ReAct loop into `core/agent/`, then extend it with the
capabilities that made the Claude Agent SDK compelling: specialist sub-agents,
bounded parallel execution, a mid-run message queue, and a lifecycle hook system.
Define the `Runtime` port so an experimental SDK adapter can exist without ever
becoming load-bearing.

## Technical context

| Aspect | Choice |
|---|---|
| Concurrency | `asyncio` throughout; sync capability bodies run in a thread executor |
| Cancellation | `asyncio.CancelledError` propagation with explicit reaping of in-flight tasks |
| Sub-agent isolation | A fresh `Session` with its own transcript; only the structured `Finding` crosses back |
| Hook dispatch | Ordered registry; hooks are async; failures caught, recorded, and swallowed except for `pre_tool_use` denial |
| Message queue | `asyncio.Queue` with a debounce window, drained at turn boundaries |
| Cache key | Tool name + canonical JSON of normalised arguments |
| Persistence | `RunTraceStore` and `SessionStore` ports (feature 006) |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | FR-008, SC-008 — every iteration traced, runs replayable offline |
| II | **This is the feature.** FR-001, FR-003, FR-004, FR-005, FR-011, FR-014 — every bound a named constant in `config/constants/investigation.py` |
| III | FR-020 — `pre_tool_use` denial is the mechanism approvals use to gate writes |
| IV | Hooks are where masking rewrites arguments before dispatch |
| V | **This is the feature.** FR-021 to FR-023 |
| VI | The loop calls `core.llm` only; SC-001 verifies termination on all nine providers |
| VII | Sub-agent and memory-hook effects are ablatable through hook registration |
| VIII | `core/agent/` is tier 3; imports `core.llm`, `core.capability`, `platform`, `config` |
| IX | Selection comes from `capabilities/registry` — the loop never improvises a capability |
| X | No egress beyond the configured provider and the credential proxy |
| XI | Session and trace persistence go through ports |
| XII | Guardrail fixtures written before the loop; SC-002 is a deterministic fixture |
| XIII | Provenance headers on ported modules |

**Violations:** none.

## Project structure

```
core/agent/
├── runtime_port.py           # Runtime protocol — the contract
├── react_loop.py             # canonical implementation
├── session.py                # Session, transcript, resumption
├── turn.py                   # Turn orchestration, accounting
├── context_budget.py         # eviction/truncation policy
├── tool_cache.py             # in-run duplicate detection
├── stagnation.py             # stagnation counter and nudge
├── seed_calls.py             # deterministic pre-loop evidence
├── conclusion.py             # pluggable acceptance policies
├── execution.py              # parallel/serial tool dispatch
├── subagents/
│   ├── definition.py         # declarative SubAgent spec
│   ├── dispatch.py           # isolation, budget, fan-out
│   └── findings.py           # structured return contract
├── message_queue.py          # mid-run user input
├── handoff.py                # human question capability
├── hooks/
│   ├── registry.py           # ordered dispatch
│   ├── types.py              # HookPoint, HookResult (including Deny)
│   └── builtin/              # tracing, accounting, budget
├── compaction.py             # transcript compaction
├── degradation.py            # partial result on LLM failure
└── adapters/
    └── claude_sdk.py         # EXPERIMENTAL — feature-flagged, never default
```

## Guardrail constants

All in `config/constants/investigation.py`.

| Constant | Default | Purpose |
|---|---|---|
| `MAX_INVESTIGATION_LOOPS` | 20 | Loop ceiling |
| `MAX_AGENT_TOOL_SCHEMAS` | 32 | Per-turn schema payload cap |
| `MAX_SECONDARY_FALLBACK_TOOLS` | 3 | Reserved slots for cheap capabilities |
| `MAX_STAGNANT_ITERATIONS` | 2 | Sterile iterations before tool access is stripped |
| `MAX_SUBAGENT_DEPTH` | 2 | Sub-agent nesting bound |
| `MAX_PARALLEL_TOOL_CALLS` | 8 | Concurrent tool execution |
| `MAX_PARALLEL_SUBAGENTS` | 4 | Concurrent sub-agent fan-out |
| `SUBAGENT_TOKEN_BUDGET_RATIO` | 0.4 | Fraction of parent budget a sub-agent may use |
| `MESSAGE_QUEUE_DEBOUNCE_MS` | 1500 | Mid-run merge window |
| `HANDOFF_TIMEOUT_SECONDS` | 900 | Human question expiry (default-deny) |
| `RUN_WALL_CLOCK_SECONDS` | 1800 | Absolute run ceiling |

## Sub-agent catalogue

Declarative, team-configurable (feature 013). Ships with these defaults:

| Sub-agent | Capability subset | Returns |
|---|---|---|
| `log-analyst` | Log stores, pattern extraction, sampling | Error signatures, temporal clusters, representative samples |
| `metrics-analyst` | Metric stores, time-series query | Change points, correlated series, anomaly windows |
| `k8s-debugger` | Kubernetes read capabilities | Events-first triage: workload state, events, recent rollouts |
| `cloud-inspector` | Cloud control-plane reads, audit logs | Recent changes, resource state, quota and limit findings |
| `code-historian` | VCS, CI, deployment platforms | Deploy timeline, correlated diffs, failing pipelines |
| `memory-recaller` | Episodic memory, knowledge base, topology | Similar past episodes, applicable playbooks, blast radius |

Each defines: capability subset, iteration budget, token budget, return schema,
and the `applies_when` conditions the parent uses to decide dispatch.

## Hook points

| Point | Signature | Used by |
|---|---|---|
| `on_run_start` | `(session) -> None` | Trace initialisation, memory recall guidance injection |
| `pre_tool_use` | `(call, context) -> Allow \| Deny \| Rewrite` | Guardrails, masking, approval gating |
| `post_tool_use` | `(call, result) -> result` | Guardrail output filtering, evidence recording |
| `on_turn_end` | `(turn) -> None` | Accounting, compaction trigger, message-queue drain |
| `on_run_end` | `(session, result) -> None` | Episode finalisation (feature 010), report delivery |
| `on_cancel` | `(session) -> None` | Reaping, state persistence |

`pre_tool_use` is the only point that can alter control flow. This is deliberate:
it is where Articles III and IV are enforced.

## Implementation phases

### Phase 1 — Port and contracts (test-first)
`runtime_port.py`, `session.py`, `turn.py`. Guardrail fixtures written and red.

### Phase 2 — Core loop
`react_loop.py`, `tool_cache.py`, `stagnation.py`, `context_budget.py`,
`seed_calls.py`, `conclusion.py`, `degradation.py`. Phase 1 fixtures go green.

### Phase 3 — Hooks
`hooks/` with ordered dispatch, `Deny`/`Rewrite` results, built-in tracing and
accounting hooks.

### Phase 4 — Execution
`execution.py` with parallel dispatch bounded by `MAX_PARALLEL_TOOL_CALLS`,
per-call failure isolation, sync-body thread offloading.

### Phase 5 — Sub-agents
`subagents/` with declarative definitions, context isolation, budget derivation,
structured findings, bounded fan-out and depth.

### Phase 6 — Interaction
`message_queue.py`, `handoff.py`, cancellation and reaping, `compaction.py`,
session resumption.

### Phase 7 — Adapter and guards
`adapters/claude_sdk.py` behind a feature flag with documented guardrail gaps; the
benchmark guard (FR-023); SC-001 across all nine providers.

## Complexity tracking

| Item | Justification |
|---|---|
| Building sub-agents rather than adopting the SDK's | ADR 0003. Roughly 1k LOC buys provider neutrality, enforceable guardrails, and reproducible trajectories — all three are constitutional requirements the SDK cannot satisfy. |
| `pre_tool_use` able to deny and rewrite | Concentrating control-flow influence at one hook point keeps the security-relevant surface small and auditable. Every other hook is observe-only. |
| Shipping an SDK adapter we will not use by default | It costs little once the port exists, and it gives teams already invested in the SDK a migration path. The guard (FR-023) prevents it from contaminating measurement. |
| Per-loop rather than per-run tool cache | A sub-agent duplicating the parent's fetch is a real trajectory inefficiency. Sharing the cache would hide it from the evaluation suite. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `tools/investigation/stages/gather_evidence/{agent,loop,tools,prompt}.py` | ADAPT → `react_loop.py`, `execution.py` |
| Tracer | `core/agent/{agent,react_loop,loop_host,goals,mixins,run_io}.py` | ADAPT |
| Tracer | `core/context_budget.py` | ADOPT |
| Tracer | `core/agent_harness/turns/` | ADAPT → `turn.py`, `compaction.py` |
| Tracer | `core/agent_harness/session/` | ADAPT → `session.py` |
| Tracer | `InvestigationToolCallCache` | ADOPT → `tool_cache.py` |
| Tracer | `CLIBackedInvestigationAgent` acceptance override | ADAPT → `conclusion.py` pluggable policies |
| Tracer | `degraded_investigation_from_llm_failure` | ADOPT → `degradation.py` |
| Swapnil | `sre-agent/agent.py` sub-agent registry and hooks | REWRITE → `subagents/`, `hooks/` |
| Swapnil | `sre-agent/message_queue.py` | ADAPT |
| Swapnil | SDK background-task lifecycle | REFERENCE → informs `subagents/dispatch.py` |
| Swapnil | `AskUserQuestion` pattern | ADAPT → `handoff.py` |

## Risks

| Risk | Mitigation |
|---|---|
| Sub-agent implementation is subtly wrong in ways only visible at scale | Sub-agents are ablatable via hook registration; the evaluation suite runs with and without them from Wave 7, so their effect is measured rather than assumed |
| Parallel execution introduces non-determinism into trajectories | The trajectory scorer treats a parallel batch as an unordered set; `parallel_safe` is opt-in per capability, so the default remains serial and deterministic |
| Cancellation leaves orphaned sub-agent tasks | Explicit reaping with a bounded wait, plus SC-006 asserting session coherence after mid-sub-agent cancellation |
| The SDK adapter drifts and becomes a support burden | Feature-flagged, documented as experimental with its guardrail gaps listed, excluded from the evaluation path by a guard test |
