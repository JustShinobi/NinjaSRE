# Feature 021 — Web Console

- **Wave:** 5 — Surfaces
- **Branch:** `feat/021-web-console`
- **Status:** Draft
- **Depends on:** 011, 012, 013, 014, 015, 016, 017, 018, 020

## Summary

The primary surface for a team: live investigations with streaming, full trace
replay, the memory hub, the configuration editor with the org tree, approval
queues, the capability catalogue, and onboarding. A client of the REST API — never
a second implementation of anything.

## User scenarios

### Primary story

An engineer opens the console mid-incident, watches the investigation stream
thought by thought, sees which capabilities were called and what they returned,
approves a proposed pod restart inline, and afterwards opens the memory hub to
find the two similar episodes the agent surfaced.

### Acceptance scenarios

1. **Given** an unauthenticated visitor, **when** they open the console, **then**
   they are directed to SSO or token sign-in, and see nothing else.
2. **Given** a running investigation, **when** it is opened, **then** events stream
   live and a network interruption recovers without losing events.
3. **Given** a completed investigation, **when** it is opened, **then** the full
   trace replays: turns, capability calls with arguments and results, sub-agent
   dispatches, evidence, guardrail actions, and cost.
4. **Given** a pending approval, **when** it is displayed, **then** it shows target,
   current state, proposed change, blast radius, and rollback plan, and can be
   decided in place.
5. **Given** a decision made elsewhere, **when** the console is open, **then** the
   pending item closes without a manual refresh.
6. **Given** the memory hub, **when** it is opened, **then** episodes are
   browsable and searchable, and strategies are viewable and editable.
7. **Given** the configuration editor, **when** a value is changed, **then** the
   effective result is previewed with per-value provenance before saving.
8. **Given** an approval-gated field, **when** it is changed, **then** the console
   shows that the change will be queued rather than applied.
9. **Given** a `viewer` role, **when** the console renders, **then** write controls
   are absent, not merely disabled.
10. **Given** an impersonating admin, **when** they act, **then** the console makes
    the impersonation visually unmistakable.

### Edge cases

- A very long investigation transcript.
- A trace with a large capability result payload.
- A slow network during a live stream.
- A user whose permissions change while the console is open.
- An org tree with hundreds of nodes.
- A configuration diff spanning thousands of lines.
- A masked identifier rendered to an authorised versus unauthorised viewer.

## Requirements

### Functional

**Investigations**

- **FR-001** A list view MUST show runs with status, trigger, team, duration, cost,
  outcome, and attention state.
- **FR-002** A detail view MUST stream a live run and replay a completed one
  through the same component.
- **FR-003** The transcript MUST render thoughts, capability calls with arguments
  and results, sub-agent dispatches, evidence, and the final report.
- **FR-004** Long transcripts MUST virtualise so rendering stays responsive.
- **FR-005** A network interruption MUST recover using the SSE cursor without
  losing or duplicating events.
- **FR-006** A user MUST be able to start an investigation, add mid-run context,
  cancel, and take over.
- **FR-007** Sub-agent dispatches MUST be expandable to show their own turns and
  calls.

**Interactions**

- **FR-008** Pending questions and approvals MUST be visible in a queue and on the
  run detail.
- **FR-009** An approval MUST display target, current state, proposed change, blast
  radius, rollback plan, and motivating evidence.
- **FR-010** Decisions made on any surface MUST propagate without a manual refresh.
- **FR-011** Executed remediations MUST offer rollback within the configured
  window.

**Memory and knowledge**

- **FR-012** Episodes MUST be browsable and searchable, showing components,
  capabilities used, resolution, effectiveness, and the run they came from.
- **FR-013** Strategies MUST be viewable with their source episodes, and editable
  with edits preserved through regeneration.
- **FR-014** Topology MUST be viewable, including dependencies and blast radius for
  a service.
- **FR-015** Knowledge documents MUST be browsable, and agent proposals reviewable.

**Configuration**

- **FR-016** The org tree MUST be navigable, and MUST remain usable with hundreds
  of nodes.
- **FR-017** Editing MUST preview the effective result with per-value provenance
  before saving.
- **FR-018** Locked fields MUST be shown as locked, naming the locking node.
- **FR-019** Approval-gated changes MUST be clearly marked as queuing rather than
  applying.
- **FR-020** Integration setup forms MUST be generated from integration schemas;
  credentials MUST post directly to the vault.
- **FR-021** The capability catalogue MUST show what is available, enabled, and why
  anything is unavailable.

**Identity and administration**

- **FR-022** Sign-in MUST support SSO and token entry.
- **FR-023** Rendering MUST be permission-aware: unavailable actions are absent,
  not disabled.
- **FR-024** Impersonation MUST be visually unmistakable throughout the session.
- **FR-025** Audit MUST be browsable and exportable with filters.
- **FR-026** Token management MUST support create, list, revoke, and bulk revoke.

**Presentation**

- **FR-027** Masked identifiers MUST be restored for authorised viewers and remain
  masked otherwise.
- **FR-028** The console MUST be responsive and usable on a phone for approvals and
  monitoring.
- **FR-029** It MUST meet WCAG 2.1 AA for the core investigation and approval
  flows.
- **FR-030** It MUST be a client of the REST API only, with no direct database
  access and no duplicated business logic.

### Key entities

| Entity | Description |
|---|---|
| **RunListView** | Filterable run history with attention state |
| **RunDetailView** | Unified live-stream and replay component |
| **InteractionQueue** | Pending questions and approvals across runs |
| **MemoryHub** | Episodes, strategies, topology, knowledge |
| **ConfigEditor** | Org tree, effective preview with provenance, diff |
| **CapabilityCatalogue** | Availability and enablement view |
| **AdminArea** | Identity, tokens, audit, policies, SSO |

## Success criteria

- **SC-001** A 10,000-event transcript renders and scrolls without a perceptible
  stall.
- **SC-002** A network interruption during a live stream recovers with no lost or
  duplicated events.
- **SC-003** A decision made in chat closes the console's pending item without a
  refresh.
- **SC-004** A `viewer` sees no write controls anywhere — asserted by a
  role-matrix test across every page.
- **SC-005** Configuration preview matches what the API actually computes, verified
  by comparing against the server's effective config.
- **SC-006** Credentials entered in the console never pass through console state or
  logs.
- **SC-007** Core investigation and approval flows pass automated accessibility
  checks.
- **SC-008** An org tree with 500 nodes remains navigable within the interaction
  budget.

## Out of scope

- The REST API itself (feature 020)
- Business logic of any kind — the console renders and calls
- Chat surfaces (feature 022)

## Clarifications

| Question | Resolution |
|---|---|
| Why must unavailable actions be absent rather than disabled? | A disabled control tells a user the capability exists and they lack it, which is information leakage about the deployment's configuration and an invitation to escalate. Absence is both safer and less confusing. |
| Why is the console a pure API client? | Any logic implemented here would need reimplementing in the CLI and the chat surfaces, and would drift. Feature 020 is the single contract all three consume. |
| Does mobile support matter? | For approvals and monitoring specifically, yes — that is what an on-call engineer does from a phone at 03:00. Full configuration editing on mobile is not a goal. |
| How are masked identifiers handled? | Restored for authorised viewers, left masked otherwise (FR-027). The console never receives the mapping for content the viewer is not authorised to see unmasked. |
