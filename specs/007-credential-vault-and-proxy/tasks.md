# Tasks — 007 Credential Vault and Proxy

## Phase 1 — Red team first (test-first)

- **T001** Write `tests/security/test_no_credentials_in_agent.py`: seed a known
  sentinel credential, run a full investigation, then assert the sentinel appears
  nowhere in the agent process environment, filesystem, prompt, tool arguments,
  transcript, or persisted trace (SC-001). Red.
- **T002** Write `tools/check_direct_credentials.py` plus a deliberate violation
  fixture (SC-003). Red.
- **T003** Write the catalogue-wide test asserting every integration routes
  through the proxy (SC-002). Red.
- **T004** Write the no-fallback test: remove the proxy, assert capability failure
  rather than degraded success (SC-005). Red.

## Phase 2 — Vault

- **T005** `platform/credentials/schemas.py`: `CredentialSchema` with field names,
  types, required/optional, validators (FR-004).
- **T006** Schemas for the first reference integrations (Datadog, Kubernetes, AWS).
- **T007** `platform/credentials/vault.py`: encrypted versioned storage over
  `CredentialStore` (FR-001, FR-002).
- **T008** Validation on write against the integration schema (FR-005).
- **T009** Metadata-only read API — presence, type, version, rotation, expiry;
  never the value (FR-003).
- **T010** Test: no code path returns a credential value outside the proxy package.

## Phase 3 — Proxy core

- **T011** `proxy/app.py`: ASGI app with the internal resolution API.
- **T012** `proxy/resolution.py`: handle + tenant + team → credential version
  (FR-007).
- **T013** `proxy/injection.py`: header, query-parameter, path-segment, body-field,
  basic-auth, bearer injections (FR-008).
- **T014** `InjectionRule` model with per-integration declarations.
- **T015** `proxy/egress.py`: allow-list enforcement from `InjectionRule.hosts`
  (FR-009).
- **T016** Test: a request to an undeclared host is rejected.
- **T017** Structured resolution errors naming integration and reason (FR-012).
- **T018** Test: no configuration enables a bypass or direct-credential mode
  (FR-010).

## Phase 4 — Signing and refresh

- **T019** `proxy/signing/sigv4.py`: proxy-side AWS SigV4.
- **T020** Test: an AWS request succeeds with no signing key in the client process
  (SC-006).
- **T021** [P] `proxy/signing/vendor.py`: other signing schemes (GCP, Azure).
- **T022** `proxy/refresh.py`: OAuth/STS refresh ahead of expiry, single retry on
  an expiry failure (FR-013).
- **T023** Test: a credential expiring mid-request is refreshed and the request
  succeeds once.

## Phase 5 — Base client

- **T024** `integrations/_base/client.py`: proxy routing, timeouts, structured
  errors (FR-015, FR-016).
- **T025** [P] `integrations/_base/retry.py`.
- **T026** [P] `integrations/_base/pagination.py`.
- **T027** [P] `integrations/_base/errors.py`.
- **T028** Rate-limit response handling with backoff.
- **T029** Reference integration on the base client: Datadog.
- **T030** Reference integration on the base client: Kubernetes.
- **T031** Reference integration on the base client: AWS (exercises proxy-side
  signing).
- **T032** Document the vendor SDK strategy decision per reference integration
  (FR-018).

## Phase 6 — Enforcement

- **T033** Wire `check_direct_credentials` into `make verify`; confirm SC-003.
- **T034** Confirm SC-002 for the reference integrations; the catalogue-wide
  assertion becomes fully meaningful in feature 025.
- **T035** Confirm SC-005 no-fallback behaviour.
- **T036** Confirm SC-001 red-team test green — the feature's defining criterion.

## Phase 7 — Operations

- **T037** `proxy/audit.py`: record tenant, team, integration, capability,
  timestamp, outcome — never the value (FR-019).
- **T038** Test: audit records contain no credential material.
- **T039** `proxy/rate_limit.py`: per-tenant limits from named constants (FR-014).
- **T040** `platform/credentials/health.py`: per-integration presence and validity
  without revealing values (FR-020).
- **T041** Startup check: stored credentials are decryptable with the configured
  key; fail at boot on mismatch.
- **T042** `platform/credentials/verification.py`: end-to-end vendor check
  reporting success or the specific failure (FR-021).
- **T043** In-process ASGI mount for the `dev` profile; same code, same behaviour
  (FR-011).
- **T044** Test: `dev` and `standard` profiles produce identical proxy behaviour.
- **T045** Confirm SC-004: rotation takes effect on the next request, no restart.
- **T046** Confirm SC-007: two teams, same vendor, different credentials, no
  cross-resolution.
- **T047** Latency benchmark asserting p50 proxy overhead within budget.
- **T048** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Red-team test finds no credential anywhere in the agent (SC-001)
- [ ] Every implemented integration routes through the proxy (SC-002)
- [ ] Direct-credential CI check fails on the violation fixture (SC-003)
- [ ] Rotation without restart (SC-004)
- [ ] Proxy outage fails closed with no fallback (SC-005)
- [ ] SigV4 works with no key in the client (SC-006)
- [ ] Per-team credential isolation (SC-007)
- [ ] `make verify` green
