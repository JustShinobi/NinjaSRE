# Feature 036 — Console Data Surfaces

- **Wave:** 9 — Console rework
- **Branch:** `feat/036-console-data-surfaces`
- **Status:** Draft
- **Depends on:** 032, 034, 035

## Summary

Every screen the console has, built from the design system inside the shell. Nine
areas: the dashboard an operator lands on, the run list and run detail, the
memory hub, the topology view, the knowledge base, the configuration editor, the
approval and interaction queue, the capability catalogue, and administration.
Plus the estate and incident views that features 038 and 039 create the data for.

The first wave shipped all of these as tables. A table is the correct answer for
about a third of them and the lazy answer for the rest. This feature decides, per
screen, what the operator is actually there to find out, and shows that.

## User scenarios

### Primary story

An operator opens the console and the first screen tells them, without scrolling,
whether anything needs them: what is running, what is waiting on a decision, what
failed, and how the estate is doing. Nothing is a number without a trend and
nothing is a status without a subject.

They click into a run. The transcript reads as a narrative — the agent's
reasoning, the capabilities it called with what arguments and what came back, the
evidence it kept, the sub-agents it dispatched, the guardrails that fired, and
the report at the end — not as a JSON dump with line breaks.

### Acceptance scenarios

1. **Given** a fresh deployment with no data, **when** any screen is opened,
   **then** it explains what would be here and what to do to get it — never a
   blank region and never a spinner that never resolves.
2. **Given** a run list of ten thousand runs, **when** it is opened, **then** it
   renders within budget, is filterable by status, trigger, team, time and
   resource, and every filter is in the URL.
3. **Given** a completed run, **when** it is opened, **then** the full trace
   replays: turns, capability calls with arguments and results, sub-agent
   dispatches, evidence, guardrail actions, tokens and cost.
4. **Given** a capability result of several megabytes, **when** it renders,
   **then** it is bounded and expandable, and the page does not stall.
5. **Given** a pending approval, **when** it is displayed, **then** it shows
   target, current state, proposed change, blast radius, risk class and rollback
   plan, and can be decided in place.
6. **Given** the memory hub, **when** it is opened, **then** episodes are
   browsable, searchable and filterable, similar episodes are shown together, and
   strategies are viewable with the anti-patterns that produced them.
7. **Given** the topology view, **when** a service is selected, **then** its
   dependencies and dependents are shown as a graph with blast radius, and the
   graph is navigable by keyboard.
8. **Given** the configuration editor, **when** a value is changed, **then** the
   effective result is previewed with per-value provenance before saving, and an
   approval-gated field says it will be queued rather than applied.
9. **Given** a `viewer` role, **when** any screen renders, **then** write
   controls are absent, not disabled.
10. **Given** an API failure on one panel, **when** it happens, **then** that
    panel shows its own error with a retry and the rest of the page still works.

### Edge cases

- A transcript with ten thousand events.
- A configuration diff spanning thousands of lines.
- An org tree with hundreds of nodes.
- A topology graph with a node that has two hundred dependents.
- A masked identifier rendered to an authorised versus an unauthorised viewer.
- A run that is still running when the page loads and finishes while it is open.
- A resource whose name is a 200-character identifier.
- Every timestamp in a locale twelve hours from the deployment's.

## Requirements

### Functional

**Dashboard**

- **FR-001** The landing screen MUST answer, above the fold: what needs a human
  now, what is running, what happened recently, and how the estate is.
- **FR-002** Attention items — pending approvals, agent questions, failed runs,
  open incidents — MUST be presented as actionable entries, each reaching its
  subject in one click.
- **FR-003** Summary figures MUST carry a period, a comparison to the previous
  period, and a link to the underlying list. A figure with no drill-down MUST NOT
  be shown.
- **FR-004** An activity feed MUST show recent events with relative timestamps,
  absolute on hover or focus, and an icon and label per event kind.

**Runs**

- **FR-005** The run list MUST show status, trigger, subject, team, duration,
  cost and attention state, and MUST be filterable and sortable with the state in
  the URL.
- **FR-006** The run detail MUST render live and completed runs through one
  component. There MUST NOT be two transcript implementations.
- **FR-007** The transcript MUST distinguish, visually and semantically: model
  reasoning, capability calls, capability results, evidence retained, sub-agent
  dispatch and return, guardrail actions, human interactions, and the final
  report.
- **FR-008** A capability call MUST show its arguments and result, bounded by
  default and expandable, with the raw payload retrievable.
- **FR-009** A run MUST show its cost and token usage, broken down by model and by
  turn.
- **FR-010** A run MUST link to the resources it touched and the incident it
  belongs to, where those exist.

**Memory, knowledge and topology**

- **FR-011** Episodes MUST be browsable and searchable, filterable by component,
  outcome and time, and each MUST link to the run that produced it.
- **FR-012** Strategies MUST be viewable with their supporting episodes and their
  anti-patterns, and editable where the viewer is permitted.
- **FR-013** The knowledge base MUST be browsable and searchable, and MUST show
  agent-proposed changes awaiting review as a queue.
- **FR-014** Topology MUST render a service and its neighbourhood as a graph,
  show blast radius, and be operable by keyboard with a list-equivalent view.

**Configuration and governance**

- **FR-015** The configuration editor MUST show the org tree, the effective
  configuration at a node, and per-value provenance — which level set it.
- **FR-016** A change MUST be previewed against the server before saving, and the
  preview MUST be the server's answer, never a client-side merge.
- **FR-017** Locked, required and approval-gated fields MUST be visually distinct
  and MUST say what will happen on save.
- **FR-018** The approval queue MUST group by urgency, show the full decision
  context, and support decide-in-place with a required reason on rejection.
- **FR-019** The audit view MUST be filterable by principal, action, subject and
  time, and exportable.

**Catalogue and administration**

- **FR-020** The capability catalogue MUST list tools and skills with domain,
  side-effect level, and which integrations they need, and MUST show which are
  enabled for the viewer's team.
- **FR-021** Integration configuration MUST show connection state, last
  verification and its result, and MUST offer a verify action.
- **FR-022** A credential field MUST post to the API origin, MUST never render a
  stored secret back, and MUST only ever be replaced.
- **FR-023** Administration MUST cover principals, grants, tokens with issuance
  and revocation, and SSO configuration.

**Universal**

- **FR-024** Every data-bearing region MUST declare an empty state that says what
  would be here and how to get it, a loading state that reserves the layout, and
  an error state with a retry scoped to that region.
- **FR-025** Every list MUST be paginated or virtualised, never truncated
  silently.
- **FR-026** Every screen MUST place its filters and selection in the URL, so a
  view can be sent to a colleague.

### Non-functional

- **NFR-001** A ten-thousand-event transcript MUST render within a declared
  budget, and the cost MUST NOT grow with the length of the transcript.
- **NFR-002** A five-hundred-node configuration tree MUST render within a declared
  budget.
- **NFR-003** No screen may block on a request it does not need to show its first
  meaningful content.
- **NFR-004** A masked identifier MUST be restored only for a viewer authorised to
  see it, and that decision MUST come from the server.

## Success criteria

- **SC-001** Every screen, with no data, renders an empty state naming the next
  action — asserted per screen.
- **SC-002** Ten thousand transcript events render within budget, with a scaling
  assertion that cost does not grow with length.
- **SC-003** One component serves both live and replayed runs, asserted
  structurally.
- **SC-004** For every role, every write control absent on every screen.
- **SC-005** A configuration preview equals the server's effective result and
  provenance, asserted against a real gateway.
- **SC-006** A failing panel leaves the rest of its page functional.
- **SC-007** Every screen's filter and selection state round-trips through the
  URL.
- **SC-008** Five hundred config nodes render within budget with every node
  present.

## Out of scope

- Live streaming and optimistic interaction — feature 037.
- The estate and incident data models — features 038 and 039.
- Proxmox-specific views — feature 048 adds them to this frame.
