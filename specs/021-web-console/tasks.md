# Tasks — 021 Web Console

## Phase 1 — Contracts and harness (test-first)

- **T001** Generate the typed API client from feature 020's OpenAPI spec.
- **T002** Client regeneration check in CI so API drift breaks the build.
- **T003** Write the role-matrix test: walk every page as every role, assert
  absence of write controls for read-only roles (SC-004). Red.
- **T004** Write the stream-recovery test: induce a network interruption, assert no
  lost or duplicated events (SC-002). Red.
- **T005** Write the accessibility harness for core investigation and approval
  flows (SC-007). Red.
- **T006** Write the transcript performance benchmark at 10,000 events (SC-001).
  Red.
- **T007** Write the config-preview parity test against the server's effective
  config (SC-005). Red.

## Phase 2 — Auth and shell

- **T008** Sign-in page: SSO redirect and token entry (FR-022).
- **T009** Session handling with expiry and re-authentication.
- **T010** Unauthenticated visitors see nothing but sign-in (acceptance scenario 1).
- **T011** Navigation shell with area routing.
- **T012** `lib/permissions.ts`: permission-aware rendering helpers using omission
  (FR-023).
- **T013** Impersonation banner, visually unmistakable throughout the session
  (FR-024).
- **T014** Light and dark themes; i18n scaffolding with English as the source
  locale.

## Phase 3 — Runs

- **T015** Run list with filters: status, team, trigger, time range, attention
  state (FR-001).
- **T016** `lib/stream.ts`: `EventSource` with `Last-Event-ID` cursor recovery
  (FR-005); confirm SC-002.
- **T017** Unified run detail component for live and replay (FR-002).
- **T018** Transcript rendering: thoughts, capability calls with arguments and
  results, evidence, final report (FR-003).
- **T019** Virtualised transcript (FR-004); confirm SC-001.
- **T020** Sub-agent dispatch expansion showing nested turns and calls (FR-007).
- **T021** Start investigation, add mid-run context, cancel, take over (FR-006).
- **T022** Cost and usage display per run.
- **T023** Masked identifier restoration for authorised viewers only (FR-027).

## Phase 4 — Interactions

- **T024** Interaction queue across runs (FR-008).
- **T025** Approval card: target, current state, proposed change, blast radius,
  rollback plan, motivating evidence (FR-009).
- **T026** Question card with structured options and free text.
- **T027** Cross-surface closure without manual refresh (FR-010); confirm SC-003
  with a decision made in chat.
- **T028** Rollback action for executed remediations within the window (FR-011).
- **T029** Pending interactions surfaced on the run detail as well as the queue.

## Phase 5 — Memory and knowledge

- **T030** Episode browse and search with components, capabilities used,
  resolution, effectiveness, originating run (FR-012).
- **T031** Strategy view with source episodes and traceability (FR-013).
- **T032** Strategy editing with edits preserved through regeneration.
- **T033** Topology explorer: dependencies, dependents, blast radius for a service
  (FR-014).
- **T034** Knowledge document browse and hierarchy (FR-015).
- **T035** Agent proposal review: approve or reject with the originating
  investigation visible.

## Phase 6 — Configuration and catalogue

- **T036** Org tree navigation remaining usable at 500 nodes (FR-016); confirm
  SC-008.
- **T037** Per-node configuration editor.
- **T038** Effective-config preview with per-value provenance before saving
  (FR-017); confirm SC-005.
- **T039** Locked fields shown as locked, naming the locking node (FR-018).
- **T040** Approval-gated changes marked as queuing rather than applying (FR-019).
- **T041** Integration setup forms generated from integration schemas (FR-020).
- **T042** Credentials posted directly to the vault, never through console state or
  logs (FR-020); confirm SC-006.
- **T043** Capability catalogue: available, enabled, unavailable with reasons
  (FR-021).
- **T044** Template application with diff preview.

## Phase 7 — Admin, accessibility, polish

- **T045** Identity management: users, roles, grants.
- **T046** [P] Token management: create, list, revoke, bulk revoke (FR-026).
- **T047** [P] Audit browse with filters and export (FR-025).
- **T048** [P] Security policy editing.
- **T049** [P] SSO configuration with test-before-activate.
- **T050** Onboarding flow mirroring the CLI wizard.
- **T051** Responsive layouts for approval and monitoring on a phone (FR-028).
- **T052** Accessibility remediation to WCAG 2.1 AA on core flows (FR-029);
  confirm SC-007.
- **T053** Confirm SC-004 role matrix green across every page.
- **T054** Verify FR-030: no direct database access and no duplicated business
  logic — a review checklist plus a dependency check.
- **T055** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] 10,000-event transcript renders without stalling (SC-001)
- [ ] Stream recovery loses and duplicates nothing (SC-002)
- [ ] Chat decisions close console items without refresh (SC-003)
- [ ] Viewers see no write controls anywhere (SC-004)
- [ ] Config preview matches server-computed effective config (SC-005)
- [ ] Credentials never pass through console state or logs (SC-006)
- [ ] Core flows pass accessibility checks (SC-007)
- [ ] 500-node org tree navigable (SC-008)
- [ ] Console is a pure API client
- [ ] `make verify` green
