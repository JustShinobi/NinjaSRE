# Tasks — 024 Integration Framework

## Phase 1 — Contract suite (test-first)

- **T001** `tests/contract/integrations/conftest.py`: catalogue discovery fixture
  parameterising the suite (FR-013).
- **T002** Assertion: credential schema validity.
- **T003** [P] Assertion: all requests route through the credential proxy.
- **T004** [P] Assertion: errors map to the shared taxonomy.
- **T005** [P] Assertion: pagination behaves per declared style.
- **T006** [P] Assertion: capability metadata completeness including
  `side_effect_level`.
- **T007** [P] Assertion: skill-to-tool binding validity.
- **T008** [P] Assertion: documentation presence.
- **T009** [P] Assertion: at least one synthetic scenario exercises the
  integration.
- **T010** Catalogue-wide no-credential-access test (SC-004). Red.

## Phase 2 — Base client

- **T011** `integrations/_base/client.py`: proxy routing, timeouts (FR-004).
- **T012** Retry with backoff over the shared taxonomy.
- **T013** Rate-limit response handling.
- **T014** [P] `_base/pagination.py`: cursor, offset, page-token styles; per-endpoint
  selection (FR-005).
- **T015** [P] `_base/errors.py`: `auth`, `permission`, `not_found`, `rate_limited`,
  `transient`, `invalid_request`, `unavailable` (FR-006).
- **T016** [P] `_base/regions.py`: regional and multi-host configuration (FR-007).
- **T017** [P] `_base/schema.py`: credential schema primitives with vault mapping.
- **T018** CI check: no integration module reads a credential-shaped environment
  variable (FR-008).

## Phase 3 — Verification framework

- **T019** `_verification/framework.py`: verifier protocol and runner (FR-009).
- **T020** `_verification/permissions.py`: permission probes derived from the
  integration's capability requirements.
- **T021** `_verification/reporting.py`: name the specific missing permission or
  connectivity problem (FR-010).
- **T022** No-verification-endpoint fallback using the cheapest read capability,
  documented (FR-011).
- **T023** Verification invocable from CLI, console, and CI (FR-012).

## Phase 4 — Catalogue

- **T024** `_catalogue/discovery.py`: package walk over `integrations/*` (FR-003).
- **T025** `_catalogue/validation.py`: seven-artefact parity check failing the
  build with both names (FR-002).
- **T026** `_catalogue/entry.py`: category, capabilities, credentials, permissions,
  regions, health, parity status (FR-021).
- **T027** `_catalogue/health.py`: degraded marking on live-run failure (FR-016).
- **T028** Catalogue exposure to the console and to documentation generation
  (FR-022).
- **T029** Live contract runs on a schedule with degraded marking rather than
  build failure (FR-015); confirm SC-006.

## Phase 5 — Domain methodology templates

- **T030** [P] `_templates/logstore.md`: statistics before samples.
- **T031** [P] `_templates/metrics.md`: baseline, change point, correlate.
- **T032** [P] `_templates/tracing.md`: exemplar, span tree, latency boundary.
- **T033** [P] `_templates/cloud_control_plane.md`: changes, state, quotas.
- **T034** [P] `_templates/database.md`: sessions and locks before plans.
- **T035** [P] `_templates/vcs.md`: deploy timeline, window diff, specific change.
- **T036** [P] `_templates/cicd.md`: last green, first failure, delta.
- **T037** [P] `_templates/ticketing.md`: search before create, link not duplicate.
- **T038** [P] `_templates/incident.md`: timeline, MTTR context, prior incidents.
- **T039** [P] `_templates/communication.md`: structured posts, link to evidence.
- **T040** [P] `_templates/data_platform.md`: lag and backlog before internals.
- **T041** Validate every template produces a skill passing binding validation
  (SC-007).

## Phase 6 — Scaffold

- **T042** `tools/scaffold_integration.py`: generate all seven artefacts as working
  stubs (FR-017).
- **T043** Provenance headers generated automatically.
- **T044** Domain parameter selecting the methodology template (FR-018).
- **T045** Generated synthetic scenario stub wired into the Wave 7 harness.
- **T046** Confirm SC-002: scaffolding edits zero existing files.

## Phase 7 — Proof

- **T047** Scaffold and complete a REST observability vendor; measure time to a
  passing contract suite.
- **T048** Scaffold and complete a cloud control-plane integration (different
  auth shape); measure.
- **T049** Scaffold and complete a database integration (non-HTTP protocol);
  measure.
- **T050** Record the three measurements against SC-001 and adjust the Wave 6
  estimate on the evidence.
- **T051** Confirm SC-003: every catalogued integration passes the contract suite.
- **T052** Confirm SC-005: verifiers name specific missing permissions.
- **T053** Contributor documentation: the seven artefacts, the scaffold, the
  templates, the contract suite.
- **T054** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Scaffold-to-passing-suite time measured on three integration shapes (SC-001)
- [ ] Adding an integration edits zero existing files (SC-002)
- [ ] Every catalogued integration passes the parameterised suite (SC-003)
- [ ] No integration client can read a credential (SC-004)
- [ ] Verifiers name specific missing permissions (SC-005)
- [ ] Vendor API breaks mark degraded rather than failing silently (SC-006)
- [ ] All eleven domain templates produce valid skills (SC-007)
- [ ] `make verify` green
