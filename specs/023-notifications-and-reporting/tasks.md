# Tasks — 023 Notifications and Reporting

## Phase 1 — Contracts (test-first)

- **T001** `platform/reporting/models.py`: `Report` with every section from FR-001.
- **T002** Add reporting and notification constants to `config/constants/`:
  cooldown windows, rate limits, retry ceiling, escalation delay, size limits.
- **T003** Write the idempotency test: transient failure then retry produces
  exactly one delivery (SC-005). Red.
- **T004** Write the redaction test: no unfiltered sensitive content reaches any
  destination (SC-006). Red.
- **T005** Write the oversize test: summarised with a link, never truncated
  (SC-007). Red.
- **T006** Write the escalation-cancellation test (SC-008). Red.
- **T007** Write the destination-isolation test (SC-002). Red.

## Phase 2 — Report building

- **T008** `platform/reporting/builder.py`: assemble a `Report` from the diagnosis
  and evidence.
- **T009** Evidence references attached to every validated claim (FR-003).
- **T010** No-conclusion path: state it plainly and present what was ruled out
  (FR-002).
- **T011** Metadata section: capabilities used, duration, cost, run link.
- **T012** Guardrail filtering before any formatting (FR-005).

## Phase 3 — Formatters

- **T013** [P] `formatters/chat.py`.
- **T014** [P] `formatters/ticket.py`: Jira, GitHub, GitLab, PagerDuty note.
- **T015** [P] `formatters/document.py`: Confluence, Notion, Google Docs.
- **T016** [P] `formatters/markdown.py`: local `report.md`.
- **T017** [P] `formatters/email.py`: HTML and plain text.
- **T018** `platform/reporting/registry.py`: destination class → formatter.
- **T019** `platform/reporting/sizing.py`: summarisation with a link when over a
  destination's limit (FR-007); confirm SC-007.

## Phase 4 — Delivery

- **T020** `delivery/dispatcher.py`: deliver to all configured destinations with
  per-destination isolation (FR-009); confirm SC-002.
- **T021** Idempotency key per run and destination; retry with backoff (FR-010);
  confirm SC-005.
- **T022** `delivery/health.py`: mark a repeatedly-failing destination unhealthy
  and surface it (FR-011).
- **T023** `delivery/verification.py`: pre-use destination check reporting a
  specific failure (FR-022).
- **T024** Delivery outcomes recorded in the run trace (FR-012).
- **T025** Handling a delivery whose team was deleted: recorded, not retried
  indefinitely.

## Phase 5 — Notification sinks

- **T026** `sinks/pushover.py`: title, message, priority, sound, run link (FR-014);
  confirm SC-003.
- **T027** [P] `sinks/email.py`.
- **T028** [P] `sinks/webhook.py`.
- **T029** [P] `sinks/pagerduty.py`.
- **T030** [P] `sinks/chat.py` delegating to feature 022's adapters.
- **T031** `notifications/redaction.py`: audience-driven redaction per sink
  (FR-018); confirm SC-006.
- **T032** Masked identifier restoration only for authorised destinations (FR-006).

## Phase 6 — Policy

- **T033** `notifications/policy.py`: routing by severity and outcome (FR-015).
- **T034** Quiet-hours policy diverting non-critical notifications (FR-023).
- **T035** `notifications/cooldown.py`: per-subject suppression with every
  suppression recorded (FR-016); confirm SC-004.
- **T036** `notifications/limits.py`: per-team rate limits (FR-017).
- **T037** Suppression and rate-limit decisions surfaced to the operator.
- **T038** Per-team destination and sink configuration through feature 013
  (FR-021).

## Phase 7 — Escalation and verification

- **T039** `notifications/escalation.py`: scheduled follow-up for unaddressed
  attention items (FR-019).
- **T040** Cancellation when the underlying item resolves (FR-020); confirm SC-008.
- **T041** Render and deliver a report to all thirteen destination types; verify
  against real or recorded responses (SC-001).
- **T042** End-to-end: an investigation concludes, the report reaches chat, ticket,
  document, and disk, and a Pushover notification arrives.
- **T043** Operator documentation: destination setup, notification policy design,
  cooldown and quiet-hours tuning, escalation configuration.
- **T044** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] All thirteen destination types render correctly (SC-001)
- [ ] One destination failure does not block the others (SC-002)
- [ ] Pushover delivers with a working link (SC-003)
- [ ] Cooldown suppresses and records (SC-004)
- [ ] Retry produces exactly one delivery (SC-005)
- [ ] No unfiltered sensitive content anywhere (SC-006)
- [ ] Oversized reports summarised with a link (SC-007)
- [ ] Escalations cancelled on resolution (SC-008)
- [ ] `make verify` green
