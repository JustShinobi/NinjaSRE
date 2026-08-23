# Feature 020 — REST API and Alert Ingestion

- **Wave:** 5 — Surfaces
- **Branch:** `feat/020-rest-api-and-alert-ingestion`
- **Status:** Draft
- **Depends on:** 005, 008, 014, 016, 018

## Summary

The programmatic surface: a REST API with SSE streaming that every other surface
consumes, plus webhook ingestion so an alert firing in Alertmanager, PagerDuty,
Datadog, Grafana, Sentry, or Opsgenie can start an investigation automatically —
with signature verification, deduplication, and backpressure.

## User scenarios

### Primary story

A team points their Alertmanager receiver at NinjaSRE. A critical alert fires at
03:00; the webhook is verified, deduplicated against the last ten minutes, and
starts an investigation. By the time the on-call engineer opens Slack, the
evidence-backed root cause is already in the thread.

### Acceptance scenarios

1. **Given** a valid token, **when** a client posts an investigation request,
   **then** a run starts and its identity is returned immediately.
2. **Given** a running investigation, **when** a client opens the SSE stream,
   **then** it receives live events; on reconnect with a cursor it receives what
   it missed.
3. **Given** a webhook from a supported source, **when** it arrives with a valid
   signature, **then** it is normalised and an investigation starts.
4. **Given** a webhook with an invalid or missing signature, **when** it arrives,
   **then** it is rejected and the attempt is audited.
5. **Given** duplicate alerts within the deduplication window, **when** they
   arrive, **then** one investigation runs and the rest are linked to it.
6. **Given** an alert storm exceeding the rate limit, **when** it arrives, **then**
   ingestion sheds load predictably and reports what it dropped — never silently.
7. **Given** an error, **when** it is returned, **then** the response contains no
   exception detail, while full detail is logged server-side.
8. **Given** a client without the required permission, **when** it calls a route,
   **then** it is denied with the required permission named.
9. **Given** an investigation with a pending question, **when** a client queries
   it, **then** the pending interaction is visible and answerable through the API.

### Edge cases

- A webhook payload much larger than expected.
- A webhook source sending a resolution event for an alert never received.
- An SSE client that stops reading but holds the connection.
- A request arriving while the platform is shutting down.
- Two webhooks for the same alert arriving simultaneously.
- A payload whose signature is valid but whose body fails schema validation.
- A client requesting a run belonging to another team.

## Requirements

### Functional

**REST API**

- **FR-001** Routes MUST cover: investigations (create, get, list, cancel),
  threads and turns, SSE streaming, mid-run message queue, interactions (list,
  answer, approve, reject), runs and traces (list, get, replay), configuration
  (read, write), integrations (list, verify), memory (search, stats), schedules,
  and health.
- **FR-002** Every route MUST declare a permission checked at the boundary
  (feature 014).
- **FR-003** Team scoping MUST be derived from the authenticated principal; a
  request MUST NOT be able to reach another team's data.
- **FR-004** Responses MUST NOT contain exception detail. Full detail is logged
  server-side (Constitution Article IV, feature 008).
- **FR-005** The API MUST be versioned, with a documented deprecation policy.
- **FR-006** An OpenAPI specification MUST be generated and served.
- **FR-007** Rate limiting MUST apply per principal and per team, with limits from
  named constants.
- **FR-008** Requests MUST carry a correlation identifier, propagated into the run
  trace.

**SSE streaming**

- **FR-009** A client MUST be able to stream a live run's events.
- **FR-010** Reconnection with a cursor MUST deliver missed events exactly once
  (feature 016).
- **FR-011** Heartbeats MUST keep the connection alive through intermediaries.
- **FR-012** A slow or stalled consumer MUST NOT block the run; it MUST be
  disconnected after a bounded buffer.
- **FR-013** The event vocabulary MUST match the pipeline's typed events
  (feature 005), so all surfaces render the same protocol.

**Webhook ingestion**

- **FR-014** Sources MUST include: Alertmanager, PagerDuty, Datadog, Grafana,
  Sentry, Opsgenie, and a generic signed webhook.
- **FR-015** Each source MUST verify authenticity using that source's mechanism
  (HMAC signature, shared secret, or mTLS).
- **FR-016** An unverified webhook MUST be rejected and audited.
- **FR-017** Payloads MUST be normalised into the pipeline's alert model
  (feature 005) by per-source adapters.
- **FR-018** Deduplication MUST link repeat alerts within a configurable window
  rather than starting new investigations.
- **FR-019** Resolution events MUST be linked to the originating investigation
  where one exists, and recorded standalone where none does.
- **FR-020** Rate limiting and load shedding MUST be explicit: what was shed MUST
  be recorded and surfaced, never silently dropped.
- **FR-021** Payload size MUST be capped, with oversize rejected with a clear
  reason.
- **FR-022** Ingestion MUST be idempotent on a source-provided event identifier
  where one exists.
- **FR-023** A webhook MUST be routable to a team by configuration, so one endpoint
  can serve multiple teams.

**Operations**

- **FR-024** Health and readiness endpoints MUST report store connectivity,
  provider availability, and migration status.
- **FR-025** Graceful shutdown MUST drain in-flight requests and mark running
  investigations resumable.

### Key entities

| Entity | Description |
|---|---|
| **InvestigationRequest** | The API-level request to start a run |
| **EventStream** | An SSE subscription with a cursor |
| **WebhookSource** | A configured inbound alert source with verification settings |
| **IngestionRecord** | The received payload, verification outcome, and routing decision |
| **DeduplicationKey** | What determines whether an alert is a repeat |
| **RateLimitDecision** | Accepted, throttled, or shed — always recorded |

## Success criteria

- **SC-001** Every route has a boundary permission check — enforced by feature
  014's route enumeration test.
- **SC-002** SSE reconnection delivers missed events exactly once under an induced
  disconnect.
- **SC-003** Webhook signature verification rejects a forged payload for every
  supported source.
- **SC-004** An alert storm of 1,000 events in a minute produces bounded
  investigations, with everything shed recorded and reportable.
- **SC-005** No error response contains exception detail — asserted across every
  route by a fault-injection test.
- **SC-006** Cross-team access is impossible through every route.
- **SC-007** A stalled SSE consumer is disconnected without affecting the run.
- **SC-008** Graceful shutdown loses no accepted request and leaves running
  investigations resumable.

## Out of scope

- Console UI (feature 021)
- Chat surfaces (feature 022)
- Outbound notification (feature 023)
- Trace persistence (feature 016)

## Clarifications

| Question | Resolution |
|---|---|
| Why does load shedding have to be reported? | Silently dropping alerts during a storm is the failure mode that destroys trust in an incident tool. An operator must be able to see exactly what was not investigated and why. |
| Is deduplication risky — could a real second incident be swallowed? | Deduplication links rather than discards (FR-018). The second alert is recorded and attached to the investigation, so nothing is lost and the operator can split them. |
| Why one endpoint for many teams? | Operators frequently have one ingress. Team routing by configuration (FR-023) avoids requiring a separate deployment or hostname per team. |
| Does the API expose everything the console needs? | Yes — the console is a client of this API (feature 021), which is what keeps the surfaces consistent. |
