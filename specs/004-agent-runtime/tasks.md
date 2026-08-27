# Tasks — 004 Agent Runtime

## Phase 1 — Port and contracts (test-first)

- **T001** `core/agent/runtime_port.py`: `Runtime` protocol — `run`, `resume`,
  `cancel`. Docstring-only bodies.
- **T002** `core/agent/session.py`: `Session` with transcript, evidence,
  accounting, status; serialisable for resumption.
- **T003** `core/agent/turn.py`: `Turn` record — model call, tool calls, usage,
  budget actions, guardrail actions.
- **T004** Populate `config/constants/investigation.py` with all eleven guardrail
  constants from the plan.
- **T005** Guardrail fixtures (all red): infinite-loop scenario, duplicate-only
  iterations, oversized evidence set, deep sub-agent nesting, parallel batch with
  partial failure, cancellation mid-sub-agent.

## Phase 2 — Core loop

- **T006** `core/agent/react_loop.py`: iteration structure with the ceiling
  (FR-001).
- **T007** `core/agent/tool_cache.py`: cache key from name + canonical normalised
  arguments; replay message telling the model it already has the result (FR-003).
- **T008** `core/agent/stagnation.py`: counter, nudge text, tool-access stripping
  at the threshold (FR-004).
- **T009** Confirm SC-002: stagnation fixture fires deterministically.
- **T010** `core/agent/context_budget.py`: eviction and truncation policy with a
  documented value function; every action recorded (FR-005).
- **T011** Golden test pinning the eviction policy's ordering decisions.
- **T012** Confirm SC-003: 8k budget, 200 evidence entries, run completes with a
  complete eviction log.
- **T013** `core/agent/seed_calls.py`: deterministic pre-loop calls by incident
  source (FR-002).
- **T014** `core/agent/conclusion.py`: pluggable acceptance — default and
  strict-until-planned-called policies (FR-006).
- **T015** `core/agent/degradation.py`: partial result on LLM failure preserving
  evidence (FR-007).
- **T016** Per-iteration trace emission (FR-008).
- **T017** Confirm SC-001 on the reference provider; defer the nine-provider run
  to Phase 7.

## Phase 3 — Hooks

- **T018** `core/agent/hooks/types.py`: `HookPoint`, `HookResult`
  (`Allow`/`Deny`/`Rewrite`).
- **T019** `core/agent/hooks/registry.py`: ordered registration and dispatch;
  failures recorded and swallowed (FR-019).
- **T020** Wire the six hook points into the loop (FR-018).
- **T021** `pre_tool_use` denial returns a structured result to the model (FR-020);
  test it.
- **T022** `pre_tool_use` argument rewrite path; test that a rewrite reaches
  execution.
- **T023** [P] Built-in tracing hook.
- **T024** [P] Built-in accounting hook.
- **T025** [P] Built-in budget hook.
- **T026** Test: a raising hook is recorded and the turn still completes.

## Phase 4 — Execution

- **T027** `core/agent/execution.py`: dispatch respecting `parallel_safe`, bounded
  by `MAX_PARALLEL_TOOL_CALLS` (FR-014).
- **T028** Per-call failure isolation within a parallel batch.
- **T029** Sync capability bodies offloaded to a thread executor.
- **T030** Reject a model-requested capability absent from the sent schema set,
  returning a structured error.
- **T031** Confirm SC-005: 10 parallel calls under 2× the slowest single call.

## Phase 5 — Sub-agents

- **T032** `core/agent/subagents/definition.py`: declarative `SubAgent` —
  capability subset, iteration and token budgets, return schema, `applies_when`.
- **T033** `core/agent/subagents/findings.py`: structured `Finding` contract
  (FR-010).
- **T034** `core/agent/subagents/dispatch.py`: isolated `Session`, budget
  derivation from `SUBAGENT_TOKEN_BUDGET_RATIO`, depth check against
  `MAX_SUBAGENT_DEPTH` (FR-009, FR-011).
- **T035** Confirm SC-004: assert the sub-agent prompt contains no parent
  transcript.
- **T036** Bounded fan-out via `MAX_PARALLEL_SUBAGENTS`; a failed sub-agent does
  not fail the parent (FR-012).
- **T037** Findings enter the parent as evidence entries with sub-agent
  provenance.
- **T038** [P] Define the six default sub-agents: `log-analyst`,
  `metrics-analyst`, `k8s-debugger`, `cloud-inspector`, `code-historian`,
  `memory-recaller`.
- **T039** Sub-agent definitions loadable from team config (FR-013); a port with a
  static default until feature 013 lands.

## Phase 6 — Interaction

- **T040** `core/agent/message_queue.py`: accept, debounce via
  `MESSAGE_QUEUE_DEBOUNCE_MS`, merge at turn boundary as one numbered block
  (FR-015).
- **T041** Emit `message_queued` on merge.
- **T042** Test: a message arriving during the final text-only turn is handled
  without reintroducing tool access.
- **T043** `core/agent/handoff.py`: human-question capability with
  `HANDOFF_TIMEOUT_SECONDS` and default-deny on expiry (FR-017).
- **T044** Cancellation: safe-point stop, in-flight reaping, consistent state
  (FR-016).
- **T045** Confirm SC-006: cancel mid-sub-agent, resume, coherent continuation.
- **T046** `core/agent/compaction.py`: summarise conversational turns while
  preserving evidence references (FR-025).
- **T047** Session persistence and resumption through the store port (FR-024).
- **T048** `RUN_WALL_CLOCK_SECONDS` ceiling independent of iteration count.

## Phase 7 — Adapter, guards, verification

- **T049** `core/agent/adapters/claude_sdk.py` implementing `Runtime`, behind a
  feature flag, never default (FR-022).
- **T050** Document the adapter's unenforceable guardrails in its module docstring
  and in `docs/`.
- **T051** Guard: any evaluation or benchmark entry point fails when the active
  runtime is not canonical (FR-023). Confirm SC-007.
- **T052** Confirm SC-001 across all nine providers.
- **T053** Confirm SC-008: replay a full run offline from its trace alone.
- **T054** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Loop terminates within the ceiling on all nine providers (SC-001)
- [ ] Stagnation breaker deterministic (SC-002)
- [ ] Tight-budget run completes with a full eviction log (SC-003)
- [ ] Sub-agent context isolation asserted (SC-004)
- [ ] Parallel execution within the latency bound (SC-005)
- [ ] Cancel-and-resume coherent (SC-006)
- [ ] Benchmark guard rejects the non-canonical runtime (SC-007)
- [ ] Offline trace replay works (SC-008)
- [ ] `make verify` green
