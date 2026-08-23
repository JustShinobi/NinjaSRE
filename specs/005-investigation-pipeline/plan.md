# Plan — 005 Investigation Pipeline

## Summary

Port Tracer's six-stage pipeline into `core/pipeline/`, with stages as pure
functions over a sliced `AgentState`. Add the deduplication and zero-integration
paths neither upstream handles well, and define the typed streaming protocol that
every surface consumes.

## Technical context

| Aspect | Choice |
|---|---|
| Stage signature | `async (state: AgentState) -> StateUpdates` |
| State merge | One `apply_state_updates` function; slices are frozen dataclasses replaced wholesale |
| Slice ownership | Declared per stage; enforced by a test, not convention |
| Structured output | `core.llm.invoke_structured` with the diagnosis model |
| Taxonomy | Versioned registry in `core/domain/diagnosis/taxonomy.py` |
| Streaming | Typed event dataclasses; SSE serialisation lives in `gateway` (feature 020) |
| Alert normalisation | Per-source adapters in `core/domain/alerts/` |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | **Central to this feature.** FR-021 and SC-003 — a claim is validated only if it references real evidence |
| II | `tool_budget`, noise threshold, and dedup window are named constants; the loop's bounds come from feature 004 |
| III | `deliver` never executes a remediation; remediation steps are recommendations until feature 017 gates them |
| IV | Evidence passes the guardrail engine before persistence (feature 008 hooks) |
| V | The pipeline invokes the canonical runtime through the port |
| VI | Both LLM calls (`intake`, `diagnose`) go through the provider abstraction |
| VII | The pipeline emits the fields episode extraction consumes; the memory hook attaches at `on_run_end` |
| VIII | `core/pipeline/` is tier 3; delivery transports live in `platform/reporting` |
| IX | Planning and gathering only ever use the resolved catalogue |
| X | No egress except configured provider, credential proxy, and configured destinations |
| XI | State and evidence persist through ports |
| XII | Stage purity (SC-004) and evidence-backing (SC-003) are tests, written first |
| XIII | Provenance headers on ported stages |

**Violations:** none.

## Project structure

```
core/pipeline/
├── lifecycle.py                 # stage ordering, merge, error handling
├── state_factory.py             # initial state construction
├── streaming.py                 # typed event definitions and emission
├── stages/
│   ├── resolve_integrations.py
│   ├── intake/
│   │   ├── node.py              # classification + extraction
│   │   ├── normalisation.py     # per-source alert adapters
│   │   ├── window.py            # incident window derivation
│   │   └── dedup.py             # recent-incident linking
│   ├── plan_evidence.py
│   ├── gather_evidence.py       # thin: invokes the runtime
│   ├── diagnose/
│   │   ├── node.py              # structured output call
│   │   ├── models.py            # Diagnosis pydantic model
│   │   ├── validation.py        # claim → evidence backing (FR-021)
│   │   └── fallback.py          # documented degraded parser
│   └── deliver.py
core/state/
├── agent_state.py               # envelope + apply_state_updates
├── slices.py                    # chat, investigation, evidence, accounting,
│                                #   approvals, memory
├── evidence.py                  # EvidenceEntry
└── types.py
core/domain/
├── alerts/                      # source mapping, field extraction, normalisation
├── correlation/                 # scoring, confidence
└── diagnosis/
    ├── taxonomy.py              # versioned RootCauseCategory registry
    ├── result.py
    └── alignment.py             # category alignment helpers
```

## Stage contract

| Stage | Reads | Writes (declared slice) | LLM calls |
|---|---|---|---|
| `resolve_integrations` | team config | `investigation.catalogue` | 0 |
| `intake` | raw input, catalogue | `investigation.alert`, `investigation.window`, `chat` | 1 |
| `plan_evidence` | alert, catalogue | `investigation.plan` | 0 |
| `gather_evidence` | alert, plan, catalogue | `evidence`, `investigation.conclusion`, `accounting` | many (runtime) |
| `diagnose` | conclusion, evidence | `investigation.diagnosis` | 1 |
| `deliver` | diagnosis, evidence | `investigation.delivery` | 0 |

`plan_evidence` uses no LLM call: scoring is deterministic (feature 003, SC-005),
which keeps the plan reproducible for trajectory evaluation.

## Root cause taxonomy

Versioned and closed, so the evaluation suite can score `root_cause_category`
exactly. Initial vocabulary:

`resource_exhaustion`, `configuration_error`, `dependency_failure`,
`code_defect`, `deployment_regression`, `capacity_limit`, `network_failure`,
`data_quality`, `security_event`, `infrastructure_failure`, `external_provider`,
`scheduled_maintenance`, `healthy`, `unknown`

Adding a category is a versioned change, because answer keys reference it.

## Implementation phases

### Phase 1 — State and contracts (test-first)
`core/state/` slices, `apply_state_updates`, `EvidenceEntry`, the stage protocol,
and the slice-ownership purity test (red).

### Phase 2 — Streaming
Typed events, emission points, and the persisted-event replay test.

### Phase 3 — Intake
Classification, per-source normalisation adapters, incident window derivation,
deduplication. SC-001 lands here.

### Phase 4 — Resolution and planning
`resolve_integrations` with the zero-integration path (FR-007, SC-006);
`plan_evidence` over the deterministic scorer.

### Phase 5 — Gathering
Thin stage invoking the runtime; evidence recording with provenance; incident
window enforcement on time-bounded calls.

### Phase 6 — Diagnosis
Structured-output model, taxonomy registry, claim-to-evidence validation (FR-021),
documented fallback parser.

### Phase 7 — Delivery and integration
`deliver` with per-destination isolation, `on_run_end` hook firing, end-to-end run
against a synthetic scenario (SC-002), corpus-wide evidence-backing assertion
(SC-003).

## Complexity tracking

| Item | Justification |
|---|---|
| Six stages rather than one agent loop | The three cheap stages around the loop (`intake`, `plan_evidence`, `diagnose`) are what make the expensive one bounded and measurable. Upstream evidence: noise short-circuit removes cost from the most common input, and structured diagnosis is what the answer keys score against. |
| Separate `diagnose` LLM call | The loop's final turn is context-pressured and often tool-stripped. Isolating structuring into its own call with only conclusion and evidence in scope is more reliable and independently testable. |
| Slice ownership enforced by test | Pure-function stages are only pure if nothing writes outside its slice. Convention does not survive twenty contributors; a test does. |
| Deduplication at intake | Neither upstream deduplicates well, and alert storms are the normal case in production. Linking rather than re-investigating is cheaper and produces a better incident record. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `tools/investigation/lifecycle.py` | ADAPT → `core/pipeline/lifecycle.py` |
| Tracer | `tools/investigation/stages/{intake,plan_evidence,resolve_integrations,diagnose}/` | ADAPT |
| Tracer | `tools/investigation/stages/gather_evidence/` | ADAPT — thinned; the loop moved to feature 004 |
| Tracer | `core/state/` | ADAPT — extended with approvals and memory slices |
| Tracer | `core/domain/{alerts,correlation,diagnosis}/` | ADOPT |
| Tracer | `core/domain/types/{evidence,incident_window,planning,root_cause_categories}.py` | ADOPT |
| Tracer | `core/llm/parsers/root_cause.py` | ADAPT → `diagnose/fallback.py` |
| Tracer | `tools/investigation/streaming.py` | ADAPT → `core/pipeline/streaming.py` |
| Swapnil | `sre-agent/events.py` SSE event vocabulary | ADOPT → event names align with the upstream protocol |

## Risks

| Risk | Mitigation |
|---|---|
| Noise classification rejects a real incident | The threshold is a constant tuned against the synthetic corpus, and every noise decision is recorded with its confidence so false negatives are auditable |
| Claim-to-evidence validation is too strict and empties `validated_claims` | The corpus-wide assertion (SC-003) runs alongside accuracy scoring, so over-strictness shows up immediately as a scoring regression |
| Taxonomy churn invalidates answer keys | The registry is versioned; a category change is a deliberate migration with answer-key updates in the same change |
| Deduplication links unrelated incidents | Linking is non-destructive — the second alert is recorded and attached, never discarded — and the window is a tunable constant |
