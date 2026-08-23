# Feature 027 — Synthetic Scenario Harness

- **Wave:** 7 — Evaluation
- **Branch:** `feat/027-synthetic-scenario-harness`
- **Status:** Draft
- **Depends on:** 004, 005, 024
- **Blocks:** 028, 029

## Summary

Deterministic incident scenarios with ground-truth answer keys, served through
mock vendor backends so an investigation runs end to end without credentials or a
live cluster. This is the substrate the entire evaluation half of the product
stands on.

## User scenarios

### Primary story

A contributor changes the capability-selection scorer. They run
`make test-synthetic` and see, in under ten minutes and with no cloud access, that
scenario 004 now takes six iterations instead of three and scenario 012 no longer
identifies the root cause. They fix it before opening a pull request.

### Acceptance scenarios

1. **Given** a scenario directory, **when** it loads, **then** its fixtures
   validate against the declared schemas and a malformed fixture fails with a
   specific message.
2. **Given** a scenario, **when** it runs, **then** mock backends serve the
   recorded vendor responses and no real credential or network access is required.
3. **Given** the same scenario and the same model, **when** it runs twice, **then**
   the trajectory is identical for a deterministic provider configuration.
4. **Given** a scenario with adversarial signals, **when** it runs, **then** the
   planted confounders are present in the evidence the agent can see.
5. **Given** a scenario with a difficulty level, **when** the suite runs, **then**
   results are reportable by level so a curriculum effect is visible.
6. **Given** a scenario run, **when** it completes, **then** a per-attempt verdict
   record is written with the full scoring detail, not just pass or fail.
7. **Given** a capability the scenario does not provide evidence for, **when** the
   agent calls it, **then** the mock backend returns an empty-but-valid response
   rather than an error.
8. **Given** a new integration, **when** it ships, **then** adding its scenario
   requires only a directory of fixtures and an answer key.

### Edge cases

- A scenario whose evidence is internally inconsistent.
- An agent calling a capability with arguments no recorded response covers.
- A scenario that no model solves, making it useless as a signal.
- A scenario every model solves trivially, likewise.
- Fixture drift when a vendor's real response shape changes.
- A scenario whose answer key keywords appear coincidentally in unrelated output.

## Requirements

### Functional

**Fixture format**

- **FR-001** A scenario MUST be a directory containing: `scenario.yml` (metadata),
  `alert.json` (the trigger), evidence fixtures, and `answer.yml` (ground truth).
- **FR-002** `scenario.yml` MUST declare: id, schema version, failure mode,
  severity, difficulty (1–4), available evidence sources, and adversarial signals.
- **FR-003** `answer.yml` MUST declare: `root_cause_category`,
  `required_keywords`, `model_response` (a reference answer), and MAY declare
  `equivalent_root_cause_categories`, `forbidden_categories`,
  `forbidden_keywords`, `required_evidence_sources`, `optimal_trajectory`,
  `golden_trajectory`, `max_investigation_loops`, `ruling_out_keywords`, and
  `required_queries`.
- **FR-004** All fixtures MUST validate against typed schemas with specific error
  messages naming file and field.
- **FR-005** Controlled vocabularies (failure modes, evidence sources, trajectory
  actions, root-cause categories) MUST be validated so a typo is a load error, not
  a silent mismatch.
- **FR-006** A scenario MAY inherit from a base scenario, overriding only what
  differs.

**Mock backends**

- **FR-007** Mock backends MUST serve recorded vendor responses through the same
  client path a real integration uses, so the agent cannot distinguish them.
- **FR-008** A capability call with no matching recorded response MUST return an
  empty-but-valid response of the correct shape, never an error.
- **FR-009** Backends MUST cover, at minimum, the tier-1 integrations, and MUST be
  extensible per integration.
- **FR-010** Backends MUST record every call so trajectory scoring can see what the
  agent actually did.
- **FR-011** Mock responses MUST be generated from recorded live responses where
  possible, with a documented recording procedure.

**Runner**

- **FR-012** The runner MUST execute a scenario end to end through the canonical
  runtime and the real pipeline — mocking only the vendor boundary.
- **FR-013** It MUST support running one scenario, a suite, or a filtered subset.
- **FR-014** It MUST support N attempts per scenario for variance measurement.
- **FR-015** Runs MUST be deterministic for a deterministic provider
  configuration.
- **FR-016** It MUST work with no credentials and no network access beyond the
  configured model endpoint.
- **FR-017** It MUST support a fully offline mode using a recorded model transcript,
  for CI paths that must not spend tokens.

**Verdict records**

- **FR-018** Every attempt MUST write a JSONL record containing: suite, scenario,
  attempt, pass or fail, difficulty, failure mode, the agent's root cause, and the
  full scoring detail.
- **FR-019** Records MUST be sufficient to reconstruct why an attempt failed
  without re-running it.
- **FR-020** Record writing MUST be off by default and enabled by an environment
  variable, so normal runs pay nothing.

**Curriculum**

- **FR-021** Difficulty levels MUST be defined and documented: 1 single obvious
  cause, 2 one confounder, 3 multiple plausible causes, 4 misleading primary
  signal.
- **FR-022** Adversarial signals MUST be declared per scenario so the suite can
  report resistance separately from accuracy.

### Key entities

| Entity | Description |
|---|---|
| **Scenario** | A directory of fixtures plus metadata and an answer key |
| **AnswerKey** | The ground truth, including trajectory and adversarial expectations |
| **MockBackend** | A recorded vendor response server on the real client path |
| **ScenarioRun** | One attempt with its trajectory and outcome |
| **VerdictRecord** | The JSONL scoring detail for one attempt |
| **Curriculum** | The difficulty stratification |

## Success criteria

- **SC-001** The full suite runs with no credentials and no cloud access.
- **SC-002** A scenario produces an identical trajectory across two runs with a
  deterministic provider configuration.
- **SC-003** A malformed fixture fails to load with a message naming file and
  field.
- **SC-004** A verdict record is sufficient to explain a failure without re-running
  — verified by having someone diagnose from records alone.
- **SC-005** Adding a scenario for a new integration requires only fixtures and an
  answer key, no code.
- **SC-006** Offline mode runs the suite with zero token spend.
- **SC-007** Results are reportable by difficulty level, showing a curriculum
  gradient.
- **SC-008** The tier-1 suite completes within the CI time budget.

## Out of scope

- Scoring logic and ablation (feature 028)
- Chaos and cloud e2e (feature 029)
- The scenarios' content beyond the seed corpus — feature 025 contributes one per
  integration

## Clarifications

| Question | Resolution |
|---|---|
| Why mock at the vendor boundary rather than at the capability? | Mocking capabilities would bypass the client, the proxy, pagination, and error mapping — exactly the layers where integration bugs live. Mocking the vendor response keeps everything under test. |
| How is a scenario kept honest as the product changes? | The answer key is about the incident, not the implementation. A scenario that breaks because the agent got worse is signal; one that breaks because a capability was renamed is fixed by the trajectory-action vocabulary check (FR-005). |
| What about scenarios nobody solves? | They are useful once, as a target, and then noise. The suite reports per-scenario solve rates so permanently-unsolved and trivially-solved scenarios are visible and can be retired or hardened. |
| Why offline mode? | So the architecture and contract CI paths can run the suite without spending tokens on every pull request, while the real evaluation runs on a schedule and before release. |
