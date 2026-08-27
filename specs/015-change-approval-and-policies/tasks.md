# Tasks — 015 Change Approval and Security Policies

## Phase 1 — Contracts and no-bypass proof (test-first)

- **T001** `platform/approvals/models.py`: `PendingChange`, `Decision`,
  `ChangeType`, `Conflict`, target-state fingerprint (FR-002).
- **T002** Add approval constants to `config/constants/security.py`: change
  expiry, diff size limits, reviewer notification limits.
- **T003** Write the no-bypass test: attempt to apply a gated change through every
  entry point without a decision (SC-001). Red.
- **T004** Write the self-approval refusal test, including via impersonation
  (SC-002). Red.
- **T005** Write the conflict-blocking test (SC-003). Red.
- **T006** Write the decision-time permission re-check test (SC-004). Red.
- **T007** Write the owner-bound policy maximum test (SC-006). Red.
- **T008** Write the audit-reconstruction test: a past decision's exact diff is
  recoverable (SC-007). Red.

## Phase 2 — State machine and service

- **T009** `platform/approvals/state_machine.py`: the five states and permitted
  transitions.
- **T010** Guard: transitions occur only through the service; no external caller
  can set state directly.
- **T011** `platform/approvals/service.py`: `queue` capturing the target
  fingerprint.
- **T012** `decide(approve)`: permission re-check (FR-010), fingerprint match,
  atomic application (FR-004).
- **T013** `decide(reject)`: reason preserved and surfaced to the requester
  (FR-005).
- **T014** Expiry policy closing pending changes with notification (FR-006).
- **T015** Self-approval policy enforcement (FR-007); confirm SC-002.
- **T016** Confirm SC-001 no-bypass green.
- **T017** Confirm SC-004 permission re-check green.

## Phase 3 — Conflict handling

- **T018** Fingerprint comparison at decision time (FR-008).
- **T019** Mark conflicted on divergence; require re-review against current state.
- **T020** Sibling conflict: approving one marks the others conflicted (FR-009).
- **T021** Deleted-target handling: conflicted with reason, unapprovable.
- **T022** Concurrent-decision handling: one wins, the other sees a conflict.
- **T023** Confirm SC-003 conflict-blocking green.

## Phase 4 — Security policy

- **T024** `platform/approvals/policy.py`: `SecurityPolicy` with all fields from
  the plan table (FR-014, FR-015).
- **T025** Policy evaluation at every gated write path.
- **T026** Role-independent enforcement of maximums and locked settings (FR-016);
  confirm SC-006.
- **T027** Policy-change auditing (FR-017).
- **T028** Optional approval-gating of policy changes themselves.
- **T029** Explicit queue-effect semantics on policy change; approved changes never
  retroactively invalidated (FR-018).
- **T030** Wire token lifecycle defaults into feature 014.

## Phase 5 — Presentation

- **T031** `diff/engine.py`: type-aware structured diff (FR-011).
- **T032** [P] `diff/renderers/config.py`.
- **T033** [P] `diff/renderers/prompt.py`.
- **T034** [P] `diff/renderers/capability.py`.
- **T035** [P] `diff/renderers/knowledge.py`.
- **T036** [P] `diff/renderers/remediation.py` (contract; feature 017 fills it).
- **T037** `diff/summarise.py`: large-diff summarisation with drill-down, never
  silent truncation (FR-013); confirm SC-008 on a 10,000-line diff.
- **T038** Guardrail filtering of diffs before display and audit.
- **T039** `platform/approvals/blast_radius.py`: affected nodes and teams via
  config inheritance (FR-012).

## Phase 6 — Routing and closure

- **T040** `platform/approvals/routing.py`: reviewer set from node-scoped
  permissions.
- **T041** `platform/approvals/notification.py`: notify eligible reviewers through
  configured surfaces (FR-019).
- **T042** `platform/approvals/closure.py`: publish a decision event all surfaces
  subscribe to (FR-021).
- **T043** Confirm SC-005: a decision on one surface immediately closes the
  request on all others.
- **T044** Approval action API consumable by console and chat (FR-020).

## Phase 7 — Audit and integration

- **T045** Audit queue, approval, rejection, expiry, and conflict (FR-022).
- **T046** Retain the diff in the audit record (FR-023); confirm SC-007.
- **T047** Wire configuration changes from feature 013 into the queue.
- **T048** Wire knowledge proposals from feature 012 into the queue.
- **T049** Reserve and document the remediation path for feature 017.
- **T050** Operator documentation: policy design, reviewer setup, conflict
  resolution, expiry tuning.
- **T051** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] No path applies a gated change without a decision (SC-001)
- [ ] Self-approval refused when policy forbids, including via impersonation (SC-002)
- [ ] Conflicting changes blocked from blind application (SC-003)
- [ ] Permission re-checked at decision time (SC-004)
- [ ] Cross-surface closure immediate (SC-005)
- [ ] Policy maximums bind every role including owner (SC-006)
- [ ] Past decisions reconstruct their exact diff (SC-007)
- [ ] 10,000-line diffs remain reviewable (SC-008)
- [ ] `make verify` green
