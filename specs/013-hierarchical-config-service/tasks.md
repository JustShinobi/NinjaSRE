# Tasks — 013 Hierarchical Configuration Service

## Phase 1 — Merge and hierarchy (test-first)

- **T001** Write merge goldens: nested dict recursion, list replacement, scalar
  replacement, type mismatch, null handling, four-level chain (SC-001). Red.
- **T002** Write the lock-enforcement test at every depth (SC-002). Red.
- **T003** Write the provenance test: every effective value names its source node
  (SC-005). Red.
- **T004** Write the cache-invalidation test: an org change alters every
  descendant's next resolution (SC-006). Red.
- **T005** `platform/config_service/merge.py`: deep merge with per-value
  provenance (FR-002, FR-003).
- **T006** `platform/config_service/hierarchy.py`: tree operations, ancestry,
  reparenting.
- **T007** Node deletion rejected while descendants exist, or explicit reparenting
  required (FR-004).
- **T008** Confirm merge goldens green (SC-001).

## Phase 2 — Schema

- **T009** `schema/agents.py`: prompts per role, sub-agent topology, budgets.
- **T010** [P] `schema/capabilities.py`: enable/disable, parameter overrides.
- **T011** [P] `schema/integrations.py`: active integrations, vault references,
  non-secret settings.
- **T012** [P] `schema/policies.py`: memory, strategy, knowledge, masking,
  guardrails, approvals.
- **T013** [P] `schema/surfaces.py`: channels, report destinations, notification
  sinks.
- **T014** `schema/root.py`: composed root schema (FR-010).
- **T015** Defaults sourced from `config/prompts/` and `config/constants/`, not
  stored in the database.
- **T016** Test: a node with empty configuration resolves to working defaults.

## Phase 3 — Field policies

- **T017** `field_policy.py`: `locked`, `required`, `approval_gated`,
  `allowed_values`, `max_values` (FR-005 to FR-008).
- **T018** Lock enforcement on write, naming the field and the locking node
  (FR-005); confirm SC-002.
- **T019** Required-field validation on effective config (FR-006).
- **T020** Approval-gated fields route to the queue instead of applying (FR-007);
  wired fully in feature 015.
- **T021** Allowed-values and max-values enforcement (FR-008).
- **T022** Lock-after-override conflict detection with explicit resolution
  (FR-009).

## Phase 4 — Validation

- **T023** `validation.py`: schema-shape validation with field-level errors
  (FR-011).
- **T024** Cross-reference validation against the live capability catalogue
  (FR-012); confirm SC-004.
- **T025** Cross-reference validation against the integration registry.
- **T026** Secret-shaped value rejection pointing to the vault (FR-013); confirm
  SC-007.
- **T027** Validation runs before persistence in every write path.

## Phase 5 — Effective config

- **T028** `effective.py`: root-to-leaf computation (FR-002).
- **T029** Per-value provenance recording (FR-016); confirm SC-005.
- **T030** Cache keyed on node plus hierarchy version (FR-015).
- **T031** Hierarchy version bumped by any ancestor write; confirm SC-006.
- **T032** Runtime resolution entry point: once per investigation (FR-014).
- **T033** Latency validation on a four-level hierarchy with a large config
  (SC-003).

## Phase 6 — Catalogue and templates

- **T034** `catalogue.py`: capability catalogue exposure with enabled state and
  unavailability reasons (FR-017).
- **T035** Integration schema exposure for console form rendering (FR-018).
- **T036** `templates/engine.py`: apply a template producing a reviewable diff
  before application (FR-019).
- **T037** [P] Golden template: `incident-triage-slack`.
- **T038** [P] Golden template: `ci-failure-investigation`.
- **T039** [P] Golden template: `cost-investigation`.
- **T040** [P] Golden template: `postmortem-authoring`.
- **T041** [P] Golden template: `alert-fatigue-reduction`.
- **T042** [P] Golden template: `dr-validation`.
- **T043** [P] Golden template: `observability-advisory`.
- **T044** Smoke test per template: applies cleanly and produces a working
  configuration (SC-008).

## Phase 7 — Audit and integration

- **T045** `audit.py`: actor, timestamp, node, field, previous and new value
  (FR-021).
- **T046** Guardrail filtering of audited values (FR-022).
- **T047** Concurrent-write handling on the same node with optimistic
  concurrency.
- **T048** Wire effective config into pipeline stage `resolve_integrations` and
  runtime configuration.
- **T049** Wire policy switches into memory, strategy, knowledge, masking, and
  guardrails.
- **T050** Wire sub-agent topology from config into feature 004's registry.
- **T051** Operator documentation: hierarchy design, locking strategy, template
  usage.
- **T052** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Merge goldens green across four levels (SC-001)
- [ ] Locked fields unoverridable at any depth (SC-002)
- [ ] Resolution within latency budget (SC-003)
- [ ] Dangling capability references fail at write (SC-004)
- [ ] Every effective value names its source node (SC-005)
- [ ] Cache invalidation correct through the hierarchy (SC-006)
- [ ] Secret-shaped values rejected with vault pointer (SC-007)
- [ ] All seven golden templates apply and work (SC-008)
- [ ] `make verify` green
