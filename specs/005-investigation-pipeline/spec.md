# Feature 005 — Investigation Pipeline

- **Wave:** 0 — Foundation
- **Branch:** `feat/005-investigation-pipeline`
- **Status:** Draft
- **Depends on:** 001, 002, 003, 004
- **Blocks:** 010, 020, 021, 023, 027, 028

## Summary

The six-stage pipeline that wraps the runtime and turns a raw alert into a
delivered, evidence-backed diagnosis. Stages are pure functions over shared state.
This is where noise is rejected before it costs a tool call, where the loop is
given a plan, and where free text becomes a structured root cause.

## User scenarios

### Primary story

An alert arrives from Alertmanager. The pipeline determines which integrations are
available, classifies the alert as real (not a greeting in a thread), extracts its
structured fields and incident window, scores the catalogue to produce a plan,
runs the bounded loop, parses the conclusion into a structured diagnosis, and
delivers a report where the team is already looking.

### Acceptance scenarios

1. **Given** a chat message that is not an incident, **when** the pipeline runs,
   **then** `intake` marks it noise and the pipeline stops with zero tool calls
   and zero evidence-gathering cost.
2. **Given** a genuine alert, **when** `intake` runs, **then** `alert_name`,
   `severity`, `alert_source`, affected components, error text, and a computed
   `incident_window` are extracted into state.
3. **Given** extracted alert fields, **when** `plan_evidence` runs, **then** the
   top `tool_budget` capabilities are selected with a written rationale, and the
   plan is advisory — an empty or low-confidence plan does not block the loop.
4. **Given** a plan, **when** `gather_evidence` runs, **then** the runtime executes
   under all guardrails and returns evidence plus a free-text conclusion.
5. **Given** a free-text conclusion, **when** `diagnose` runs, **then** structured
   output yields `root_cause`, `root_cause_category`, `causal_chain`,
   `validated_claims`, `non_validated_claims`, `remediation_steps`, and
   `validity_score`.
6. **Given** structured-output parsing fails, **when** `diagnose` runs, **then** a
   documented fallback parser produces a best-effort structure and records that
   the fallback was used.
7. **Given** a completed diagnosis, **when** `deliver` runs, **then** the report is
   formatted and shipped to every configured destination, and a delivery failure
   to one destination does not prevent the others.
8. **Given** any stage raises, **when** it happens, **then** the failure is
   recorded with stage identity and re-raised — never silently swallowed.
9. **Given** an investigation in progress, **when** a client subscribes, **then**
   stage transitions, thoughts, tool lifecycle, and the final result stream as
   typed events.

### Edge cases

- An alert whose source is unrecognised (no seed calls, no source-matched plan).
- Zero integrations configured — the pipeline must produce a useful "cannot
  investigate, here is what to connect" outcome rather than an empty report.
- An incident window that cannot be computed from the alert.
- A conclusion that names a root cause with no supporting evidence entry — must be
  demoted to `non_validated`.
- Two alerts for the same incident arriving within the deduplication window.
- `deliver` when the only destination is unreachable.

## Requirements

### Functional

**Pipeline structure**

- **FR-001** The pipeline MUST comprise six stages in order:
  `resolve_integrations`, `intake`, `plan_evidence`, `gather_evidence`,
  `diagnose`, `deliver`.
- **FR-002** Each stage MUST be a pure function `(state) -> updates`, with updates
  merged into shared state by a single documented merge function.
- **FR-003** A stage exception MUST be recorded with stage identity and re-raised.
  No stage may swallow a failure.
- **FR-004** `intake` marking the input as noise MUST short-circuit the pipeline
  before any capability executes.
- **FR-005** Every stage transition MUST emit a typed event on the stream.

**Stage: resolve_integrations**

- **FR-006** MUST determine which integrations the team has configured and
  credentialed, producing the `ResolvedCatalogue` (feature 003).
- **FR-007** With zero usable integrations, the pipeline MUST terminate with an
  actionable outcome naming what to connect, not an empty investigation.

**Stage: intake**

- **FR-008** MUST classify the input as incident or noise in a single LLM call.
- **FR-009** MUST extract structured fields: `alert_name`, `severity`,
  `alert_source`, affected components, error text, and metadata.
- **FR-010** MUST compute an `incident_window` (start, end, confidence) used by
  every time-bounded capability downstream.
- **FR-011** MUST support alert normalisation per source (Alertmanager, PagerDuty,
  Datadog, Grafana, Sentry, Opsgenie, generic webhook, plain text).
- **FR-012** MUST deduplicate against recent incidents within a configured window,
  linking rather than re-investigating.

**Stage: plan_evidence**

- **FR-013** MUST score the resolved catalogue against the extracted alert and
  keep the top `tool_budget` entries as `planned_actions`.
- **FR-014** MUST produce a written rationale for the plan, recorded in state.
- **FR-015** The plan MUST be advisory: the loop falls back to its own relevance
  ranking when the plan is empty or low-confidence.

**Stage: gather_evidence**

- **FR-016** MUST invoke the canonical runtime with the plan, the resolved
  catalogue, and the incident context.
- **FR-017** MUST record every evidence entry with source, capability, timestamp,
  and provenance.
- **FR-018** MUST enforce the incident window on time-bounded capability calls.

**Stage: diagnose**

- **FR-019** MUST convert the free-text conclusion into a structured diagnosis via
  provider structured output.
- **FR-020** The structured diagnosis MUST contain: `root_cause`,
  `root_cause_category` (from a closed taxonomy), `causal_chain`,
  `validated_claims`, `non_validated_claims`, `remediation_steps`,
  `validity_score`, and `confidence`.
- **FR-021** A claim MUST be classified `validated` only if it references at least
  one evidence entry present in state. Unreferenced claims MUST be demoted.
- **FR-022** A documented fallback parser MUST exist for structured-output failure,
  and its use MUST be recorded.
- **FR-023** `root_cause_category` MUST come from a versioned taxonomy registry so
  the evaluation suite can score against it.

**Stage: deliver**

- **FR-024** MUST format the diagnosis per destination and ship to all configured
  destinations.
- **FR-025** A delivery failure MUST NOT prevent other deliveries, and MUST be
  recorded.
- **FR-026** MUST fire the `on_run_end` lifecycle hook so downstream consumers
  (episode finalisation, feature 010) run exactly once.

**State and streaming**

- **FR-027** `AgentState` MUST carry slices: chat, investigation, evidence,
  accounting, approvals, memory. A stage may only write its declared slice.
- **FR-028** The streaming protocol MUST emit typed events: `stage_start`,
  `stage_end`, `thought`, `tool_start`, `tool_end`, `subagent_start`,
  `subagent_end`, `evidence`, `question`, `approval_request`, `message_queued`,
  `result`, `error`.
- **FR-029** Events MUST be serialisable to SSE and reconstructible from the
  persisted trace.

### Key entities

| Entity | Description |
|---|---|
| **AgentState** | The shared envelope with per-concern slices |
| **InvestigationSlice** | Alert fields, incident window, plan, evidence, diagnosis |
| **EvidenceEntry** | One observation: source, capability, arguments, payload, timestamp, provenance |
| **IncidentWindow** | Start, end, and confidence, derived at intake |
| **PlannedAction** | A capability plus score and rationale |
| **Diagnosis** | The structured conclusion with claims separated by validation status |
| **RootCauseCategory** | A versioned taxonomy entry |
| **StreamEvent** | A typed pipeline event |

## Success criteria

- **SC-001** A non-incident message costs zero capability executions and completes
  in a single LLM call.
- **SC-002** A synthetic scenario runs end to end producing a diagnosis whose
  `root_cause_category` matches its answer key.
- **SC-003** Every claim marked `validated` references an evidence entry present
  in state — asserted across the whole synthetic corpus.
- **SC-004** Stage purity is enforced: a test asserts no stage mutates state
  outside its declared slice.
- **SC-005** The event stream is complete — replaying persisted events
  reconstructs the full investigation view (SC parallel to feature 004's SC-008).
- **SC-006** With zero integrations configured, the outcome names the specific
  integrations that would have been used for that alert source.

## Out of scope

- Report formatting and delivery transports (feature 023)
- Alert webhook ingestion (feature 020)
- Memory recall and episode writing (feature 010)
- Approval decisions (feature 017)

## Clarifications

| Question | Resolution |
|---|---|
| Why a separate `diagnose` LLM call rather than asking the loop for structure? | The loop's final turn is often tool-access-stripped and context-pressured. A dedicated structured-output call with only the conclusion and evidence in scope is more reliable and independently testable. |
| Is the plan binding? | No. It is advisory (FR-015). A binding plan would make the agent worse when the incident is not what the alert suggested. |
| Where does the noise threshold live? | `intake` returns a classification with confidence; the threshold is a named constant so it can be tuned against the synthetic corpus rather than by intuition. |
| Can two stages run concurrently? | No. Stage ordering is sequential by design so the trajectory is well-defined. Concurrency lives inside `gather_evidence`. |
