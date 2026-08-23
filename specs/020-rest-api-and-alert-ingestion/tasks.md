# Tasks — 020 REST API and Alert Ingestion

## Phase 1 — Contracts (test-first)

- **T001** Declare every planned route in feature 014's `route_permissions.py`
  (FR-002); confirm the enumeration test covers them (SC-001).
- **T002** Write the error-sanitisation fault-injection test across every route
  (SC-005). Red.
- **T003** Write the cross-team access test for every route (SC-006). Red.
- **T004** Write signature-forgery tests per webhook source with real payload
  fixtures (SC-003). Red.
- **T005** Write the SSE reconnection exactly-once test (SC-002). Red.
- **T006** Write the stalled-consumer test (SC-007). Red.
- **T007** Write the graceful-shutdown test (SC-008). Red.
- **T008** Add API constants to `config/constants/surfaces.py`: rate limits,
  payload caps, SSE buffer size, heartbeat interval, dedup window.

## Phase 2 — API core

- **T009** `gateway/http/app.py`: FastAPI application with versioned routing.
- **T010** OpenAPI generation and serving (FR-006).
- **T011** Auth dependencies wired from feature 014 (FR-002).
- **T012** Team scoping derived from the principal (FR-003).
- **T013** `gateway/http/errors.py`: sanitised responses, full detail logged
  server-side (FR-004); confirm SC-005.
- **T014** `gateway/http/rate_limit.py`: per-principal and per-team limits (FR-007).
- **T015** Correlation identifier propagation into the run trace (FR-008).
- **T016** API version deprecation policy documented (FR-005).

## Phase 3 — Investigation routes

- **T017** `routes/investigations.py`: create, get, list, cancel.
- **T018** [P] `routes/threads.py`: threads and turns.
- **T019** Mid-run message queue endpoint (feature 018 integration).
- **T020** [P] `routes/interactions.py`: list, answer, approve, reject (FR-001).
- **T021** Pending interactions visible and answerable through the API
  (acceptance scenario 9).

## Phase 4 — Streaming

- **T022** `streaming/sse.py`: serialise feature 005's typed events (FR-013).
- **T023** `streaming/subscription.py`: cursor handling with `Last-Event-ID`
  catch-up (FR-010); confirm SC-002.
- **T024** Heartbeat frames at a fixed interval (FR-011).
- **T025** `streaming/backpressure.py`: bounded buffer, stalled-consumer
  disconnect without blocking the run (FR-012); confirm SC-007.
- **T026** Multi-subscriber support for one run.

## Phase 5 — Remaining routes

- **T027** [P] `routes/runs.py`: list, get, replay.
- **T028** [P] `routes/config.py`: read and write via feature 013.
- **T029** [P] `routes/integrations.py`: list and verify.
- **T030** [P] `routes/memory.py`: search and stats.
- **T031** [P] `routes/schedules.py`.
- **T032** [P] `routes/capabilities.py`: catalogue read for console rendering.
- **T033** `routes/health.py`: liveness, readiness reporting store connectivity,
  provider availability, migration status (FR-024).
- **T034** Confirm SC-006 cross-team isolation across every route.

## Phase 6 — Webhook ingestion

- **T035** `webhooks/router.py`: endpoint with configuration-driven team routing
  (FR-023).
- **T036** Payload size cap with a clear rejection reason (FR-021).
- **T037** [P] `verification/hmac.py`.
- **T038** [P] `verification/shared_secret.py`.
- **T039** [P] `verification/mtls.py`.
- **T040** Rejection and auditing of unverified webhooks (FR-016).
- **T041** [P] `sources/alertmanager.py`.
- **T042** [P] `sources/pagerduty.py`.
- **T043** [P] `sources/datadog.py`.
- **T044** [P] `sources/grafana.py`.
- **T045** [P] `sources/sentry.py`.
- **T046** [P] `sources/opsgenie.py`.
- **T047** [P] `sources/generic.py`.
- **T048** Normalisation into the pipeline alert model via feature 005 adapters
  (FR-017).
- **T049** `webhooks/idempotency.py`: source event-id based (FR-022).
- **T050** Confirm SC-003 forgery rejection for all seven sources.

## Phase 7 — Storm handling and lifecycle

- **T051** `webhooks/dedup.py`: fingerprint over source, alert identity, target,
  name, within the window; link rather than discard (FR-018).
- **T052** Resolution-event linking to the originating investigation, standalone
  recording where none exists (FR-019).
- **T053** `webhooks/shedding.py`: explicit shed with recording (FR-020).
- **T054** Shed decisions surfaced through the runs and health APIs so operators
  can see what was not investigated.
- **T055** Storm validation: 1,000 events in a minute, bounded investigations,
  complete shed record (SC-004).
- **T056** `gateway/http/lifespan.py`: startup checks and graceful shutdown drain
  marking running investigations resumable (FR-025); confirm SC-008.
- **T057** Operator documentation: webhook setup per source, verification
  configuration, team routing, dedup and shed tuning.
- **T058** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Every route has a boundary permission check (SC-001)
- [ ] SSE reconnection delivers missed events exactly once (SC-002)
- [ ] Forged webhooks rejected for all seven sources (SC-003)
- [ ] 1,000-event storm bounded, with a complete shed record (SC-004)
- [ ] No error response contains exception detail (SC-005)
- [ ] Cross-team access impossible through every route (SC-006)
- [ ] Stalled SSE consumers disconnected without affecting runs (SC-007)
- [ ] Graceful shutdown loses nothing (SC-008)
- [ ] `make verify` green
