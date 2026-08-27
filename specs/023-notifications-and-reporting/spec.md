# Feature 023 — Notifications and Reporting

- **Wave:** 5 — Surfaces
- **Branch:** `feat/023-notifications-and-reporting`
- **Status:** Draft
- **Depends on:** 005, 008, 013, 016, 018

## Summary

Turning a completed investigation into something a human reads, in the place they
will read it — and making sure the notification that gets them there arrives once,
at the right severity, without waking anyone unnecessarily. Includes **Pushover**
for direct push to a phone.

## User scenarios

### Primary story

An investigation concludes at 03:14. A Pushover notification reaches the on-call
engineer's phone with the one-line root cause and a link. The full report is
already in the incident's Slack thread, a Jira ticket has been created with the
evidence, and a Markdown copy is on disk. Nobody else is woken.

### Acceptance scenarios

1. **Given** a completed investigation, **when** delivery runs, **then** the report
   is formatted per destination and delivered to all configured destinations.
2. **Given** one destination fails, **when** delivery runs, **then** the others
   still receive the report and the failure is recorded.
3. **Given** a Pushover sink configured, **when** a notification fires, **then** it
   reaches the device with a title, message, priority, and a link to the run.
4. **Given** repeated notifications for the same subject, **when** they occur
   within the cooldown, **then** they are suppressed and the suppression is
   recorded.
5. **Given** a low-severity outcome, **when** notification policy is applied,
   **then** it is routed to a non-paging destination.
6. **Given** a report containing sensitive content, **when** it is delivered,
   **then** guardrails have filtered it and masked identifiers are restored only
   for authorised destinations.
7. **Given** a delivery that fails transiently, **when** it is retried, **then**
   backoff applies and duplicates are not produced.
8. **Given** an investigation that reached no confident conclusion, **when** the
   report is produced, **then** it says so plainly and lists what was ruled out.

### Edge cases

- A report longer than a destination's size limit.
- A destination configured but never verified.
- A notification for a run whose team was deleted.
- Repeated failures making a destination permanently unhealthy.
- A masked identifier in a report delivered to a partially-authorised channel.
- An escalation firing after the incident already resolved.

## Requirements

### Functional

**Report generation**

- **FR-001** A report MUST contain: summary, root cause with confidence, causal
  chain, validated claims with evidence references, non-validated claims,
  recommended actions, what was ruled out, capabilities used, duration, and cost.
- **FR-002** Where no confident conclusion was reached, the report MUST state that
  plainly and present what was ruled out (FR acceptance 8).
- **FR-003** Every validated claim MUST carry a reference to the evidence entry
  behind it.
- **FR-004** Formatters MUST exist per destination class: chat, ticket, document,
  Markdown file, and email.
- **FR-005** Reports MUST pass the guardrail engine before delivery.
- **FR-006** Masked identifiers MUST be restored only for destinations whose
  audience is authorised.
- **FR-007** A report exceeding a destination's size limit MUST be summarised with
  a link to the full version, never silently truncated.

**Delivery**

- **FR-008** Destinations MUST include: Slack, Teams, Telegram, Discord, Jira,
  GitLab, GitHub, Confluence, Notion, Google Docs, PagerDuty, local Markdown, and
  email.
- **FR-009** Delivery MUST be per-destination isolated: one failure MUST NOT
  prevent others.
- **FR-010** Transient failures MUST retry with backoff and MUST NOT produce
  duplicates.
- **FR-011** A destination failing repeatedly MUST be marked unhealthy and surfaced
  to the operator.
- **FR-012** Delivery outcomes MUST be recorded in the run trace.

**Notification sinks**

- **FR-013** Sinks MUST include **Pushover**, plus email, webhook, PagerDuty, and
  the chat platforms.
- **FR-014** Pushover MUST support title, message, priority, sound, and a link
  back to the run.
- **FR-015** Notification policy MUST route by severity, outcome, and team
  configuration.
- **FR-016** Cooldown MUST suppress repeat notifications for the same subject
  within a window, recording every suppression.
- **FR-017** Rate limits MUST bound notifications per team per period.
- **FR-018** Notification content MUST be redacted at the sink; a sink's audience
  determines what it may contain.
- **FR-019** Escalation MUST be supported: if an attention item is unaddressed
  after a period, escalate to a configured destination.
- **FR-020** An escalation MUST be cancelled if the underlying item resolves first.

**Configuration**

- **FR-021** Destinations and sinks MUST be configured per team through the config
  service.
- **FR-022** Each MUST be verifiable before use, reporting a specific failure.
- **FR-023** A quiet-hours policy MUST be supported, routing non-critical
  notifications to a non-paging destination.

### Key entities

| Entity | Description |
|---|---|
| **Report** | The structured investigation output, before formatting |
| **Formatter** | Destination-class-specific rendering |
| **Destination** | A configured report target |
| **NotificationSink** | A configured notification target, including Pushover |
| **NotificationPolicy** | Severity, outcome, quiet hours, escalation routing |
| **Cooldown** | Per-subject suppression window |
| **DeliveryRecord** | Outcome per destination, retained in the trace |

## Success criteria

- **SC-001** A report delivered to all thirteen destination types renders correctly
  in each — verified against real or recorded destination responses.
- **SC-002** A single destination failure does not prevent the others.
- **SC-003** Pushover delivers with title, message, priority, and a working link.
- **SC-004** Cooldown suppresses repeats and records every suppression.
- **SC-005** Retry after a transient failure produces exactly one delivery.
- **SC-006** No unfiltered sensitive content reaches any destination.
- **SC-007** An oversized report is delivered summarised with a link, never
  truncated silently.
- **SC-008** An escalation is cancelled when its underlying item resolves first.

## Out of scope

- Chat interaction handling (feature 022 — this feature produces content, that one
  handles conversation)
- The investigation itself (feature 005)
- Alert ingestion (feature 020)

## Clarifications

| Question | Resolution |
|---|---|
| Why is Pushover called out specifically? | Direct push to a phone without a chat platform in the path. For a small team without Slack, or for an escalation that must not depend on the same system that may be having the incident, it is the shortest path to a human. |
| Why must a no-conclusion report be explicit? | Constitution Article I. A report that hedges its way to a plausible-sounding cause is worse than one that says "I could not determine this, here is what I ruled out" — the second saves the engineer the work of re-ruling-out. |
| Why redact at the sink rather than at generation? | Different destinations have different audiences. One report generation, per-sink redaction, means a private incident channel can see what a public status page cannot. |
| Does every destination need verification? | Yes (FR-022). An unverified destination fails at 03:00, which is the worst possible time to discover a wrong API token. |
