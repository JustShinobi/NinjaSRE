# Tasks — 014 Identity, RBAC, SSO, and Audit

## Phase 1 — Model and enforcement contracts (test-first)

- **T001** `platform/identity/permissions.py`: atomic permission catalogue and the
  five role definitions (FR-007).
- **T002** `platform/identity/models.py`: `Principal`, `Role`, `Permission`,
  `Grant`, `Token`, `Session`.
- **T003** Write `tests/security/test_route_permissions.py`: walk the router,
  assert every non-public route declares a permission (SC-001). Red.
- **T004** Write `tests/security/test_audit_immutability.py`: attempt update and
  delete through the repository and through raw SQL; both must fail (SC-003). Red.
- **T005** Write the last-owner protection test (SC-005). Red.
- **T006** Write the impersonation dual-principal test across every audited action
  type (SC-004). Red.
- **T007** Add identity constants to `config/constants/security.py`: session idle
  and absolute limits, token expiry defaults, inactivity threshold, warning
  window, break-glass duration.

## Phase 2 — Principals and authorisation

- **T008** `platform/identity/authorisation.py`: node-scoped permission resolution
  with descendant inheritance (FR-009).
- **T009** `gateway/http/security/dependencies.py`: `requires(Permission)`
  boundary dependency (FR-008).
- **T010** `gateway/http/security/route_permissions.py`: the declared route →
  permission map.
- **T011** Denial messages naming the required permission and scope (FR-010).
- **T012** Last-owner protection (FR-011); confirm SC-005.
- **T013** Confirm SC-001 route enumeration green for the routes existing so far;
  the test remains active as routes are added in later features.

## Phase 3 — Tokens

- **T014** `platform/identity/tokens.py`: issue with a salted hash and a
  identifying prefix; plaintext shown once and never retrievable (FR-005).
- **T015** Token scoping: org, team, permission set, expiry, description (FR-004).
- **T016** Verification with clock-skew tolerance.
- **T017** Immediate revocation with cache invalidation broadcast (FR-019);
  confirm SC-002.
- **T018** Inactivity-based automatic revocation with owner notification (FR-020).
- **T019** Expiry warnings at a configurable lead time (FR-021).
- **T020** Bulk revocation for incident response (FR-022).
- **T021** Handling of a token whose team was deleted: rejected with a clear
  reason.

## Phase 4 — Sessions and OIDC

- **T022** `platform/identity/sessions.py`: issue, validate, idle and absolute
  limits (FR-006).
- **T023** Server-side revocation list for sessions.
- **T024** `platform/identity/oidc.py`: Authorization Code with PKCE (FR-001).
- **T025** Claim extraction and group-to-team mapping (FR-012).
- **T026** Group re-evaluation at each sign-in (FR-013).
- **T027** No-group-claims fallback to the default team, recorded (FR-014).
- **T028** `platform/identity/sso_config.py`: test-before-activate (FR-015);
  confirm SC-006.
- **T029** Concurrent sessions for one user across surfaces.

## Phase 5 — Impersonation and break-glass

- **T030** `platform/identity/impersonation.py`: time-limited admin context switch
  (FR-016, FR-018).
- **T031** Dual-principal recording on every action (FR-017); confirm SC-004.
- **T032** Console-visible distinction contract for feature 021.
- **T033** `platform/identity/break_glass.py`: local admin path, time-limited
  (FR-002).
- **T034** Prominent audit for break-glass use; confirm SC-007 with SSO
  unavailable.

## Phase 6 — Audit

- **T035** `platform/identity/audit/recorder.py`: record principal, impersonation
  context, timestamp, action, target, outcome, source address (FR-024).
- **T036** Durable fallback plus alert on audit write failure (FR-028).
- **T037** `platform/identity/audit/guard.py`: repository exposes append and read
  only.
- **T038** Database trigger rejecting `UPDATE` and `DELETE` on the audit table.
- **T039** Confirm SC-003 immutability test green through both paths.
- **T040** Retention exemption for audit records (FR-026).
- **T041** `platform/identity/audit/export.py`: SIEM-ingestible export (FR-027);
  confirm SC-008.

## Phase 7 — Integration

- **T042** Thread the acting principal through the runtime so capability execution
  is attributable.
- **T043** Audit authentication events.
- **T044** [P] Audit token lifecycle events.
- **T045** [P] Audit configuration changes (integrating feature 013).
- **T046** [P] Audit credential changes (integrating feature 007).
- **T047** [P] Audit permission and role changes.
- **T048** Audit hooks reserved for approvals and remediation (features 015, 017).
- **T049** Operator documentation: role model, SSO setup, break-glass procedure,
  audit export.
- **T050** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Every privileged route has a declared permission check (SC-001)
- [ ] Revoked tokens rejected immediately (SC-002)
- [ ] Audit records immutable through every path (SC-003)
- [ ] Impersonation records both principals everywhere (SC-004)
- [ ] An org can never lose its last owner (SC-005)
- [ ] SSO testable before activation (SC-006)
- [ ] Break-glass works with SSO down, time-limited and audited (SC-007)
- [ ] Audit export SIEM-ingestible (SC-008)
- [ ] `make verify` green
