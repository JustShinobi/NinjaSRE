# Feature 037 — Console Live Layer

- **Wave:** 9 — Console rework
- **Branch:** `feat/037-console-live-layer`
- **Status:** Draft
- **Depends on:** 032, 036

## Summary

What makes the console feel like it is connected to something: a run whose
transcript grows as the agent thinks, an approval card that closes when a
colleague decides it in Slack, a toast when a remediation lands, a drawer that
starts an investigation without leaving the page.

This is the half of the console the first wave could not build. `live.py` and
`stream.py` implemented the *mapping* from stream event to screen change and
tested it at that seam — correctly, and it is the right seam — but with no
client-side runtime there was nothing to apply the mapping in a browser. This
feature is that runtime, and it must preserve the property the mapping already
proved: every event exactly once, in order, across a reconnection.

## User scenarios

### Primary story

An operator opens a running investigation. Thoughts, tool calls and results
appear as they happen. Their laptop sleeps; they open it twenty minutes later and
the transcript fills in the gap rather than starting over or skipping it. Halfway
down, the agent asks a question — they answer it in place and the run continues.

Meanwhile a colleague approves a pending restart from Slack. The card on this
operator's screen closes itself and says who decided it.

### Acceptance scenarios

1. **Given** a running investigation, **when** it is open, **then** events appear
   as they occur without a manual refresh.
2. **Given** an interrupted connection, **when** it recovers, **then** every event
   is delivered exactly once, in sequence order, with the gap filled from the
   cursor and no duplicates.
3. **Given** a stream that cannot be re-established, **when** retries are
   exhausted, **then** the console says so plainly and offers a manual reload;
   it MUST NOT silently show a stale transcript as if it were live.
4. **Given** a pending approval open on screen, **when** it is decided anywhere
   else, **then** the card closes and names the decider, without a refresh.
5. **Given** an agent question, **when** it arrives, **then** it is answerable in
   place, and answering it resumes the run.
6. **Given** an approval decided in the console, **when** the decision is
   submitted, **then** the UI reflects it immediately and reverts with an
   explanation if the server refuses.
7. **Given** a run that completes while open, **when** it completes, **then** the
   view becomes the completed view without reloading and without losing scroll
   position.
8. **Given** a long-running transcript, **when** the operator has scrolled up,
   **then** new events do not yank the viewport; a control says how many arrived.
9. **Given** any background action, **when** it succeeds or fails, **then** a
   toast reports it and the outcome is also visible somewhere durable — a toast
   is never the only record.
10. **Given** a takeover, **when** an operator takes control of a run, **then**
    the run pauses at its next safe point and the console says it has.

### Edge cases

- Two tabs open on the same run.
- A stream delivering events out of order.
- A stream that replays events already seen after a reconnect.
- A run cancelled by someone else while open.
- Ten thousand events arriving in a burst after a long disconnection.
- A token expiring mid-stream.
- The browser throttling a background tab.
- A drawer open when the underlying record is deleted.

## Requirements

### Functional

**Streaming**

- **FR-001** A live run MUST subscribe to the run's event stream and apply events
  to the same transcript component the replay uses.
- **FR-002** Every applied event MUST be recorded against a cursor, and a
  reconnection MUST resume from that cursor.
- **FR-003** Duplicate events MUST be discarded by sequence, and out-of-order
  events MUST be ordered before rendering.
- **FR-004** Reconnection MUST back off, MUST be bounded, and MUST surface its
  state — connected, reconnecting, disconnected — where the operator can see it.
- **FR-005** A disconnected stream MUST NOT present itself as live.
- **FR-006** A stream MUST be torn down when its view closes; no subscription may
  outlive the screen that opened it.
- **FR-007** A token expiring mid-stream MUST end the session through the same
  single-collapse path as any other 401.

**Cross-surface closure**

- **FR-008** An attention item resolved on any surface MUST close in the console
  without a refresh, and MUST name who resolved it and where.
- **FR-009** A closed item MUST offer no decision to anybody, in any tab.

**Interaction**

- **FR-010** An agent question MUST be answerable in place, and the answer MUST
  resume the run.
- **FR-011** An approval MUST be decidable in place, with a required reason on
  rejection.
- **FR-012** An operator MUST be able to take over a run, pausing it at its next
  safe point, and to resume or cancel it.
- **FR-013** An operator MUST be able to add context to a running investigation
  without stopping it.
- **FR-014** Starting a new investigation MUST be possible from anywhere through
  a drawer, without leaving the current page.

**Optimism and feedback**

- **FR-015** A write the operator initiated MUST be reflected immediately and MUST
  revert with a stated reason if the server refuses.
- **FR-016** A toast MUST NOT be the only record of an outcome.
- **FR-017** Any action that cannot be undone MUST require a confirmation naming
  the target and the consequence.

**Live data elsewhere**

- **FR-018** Lists that change while open — runs, approvals, incidents — MUST
  update without a full refetch, and MUST not reorder under the operator's
  pointer.
- **FR-019** The notification centre MUST update from the same event source as
  the screens, so a count and a list cannot disagree.

### Non-functional

- **NFR-001** A burst of ten thousand events after a reconnection MUST be applied
  within a declared budget without blocking interaction.
- **NFR-002** A background tab MUST reduce its work and MUST recover fully on
  return.
- **NFR-003** Event application MUST be pure and independently testable, with no
  DOM dependency, so the exactly-once property is provable without a browser.
- **NFR-004** No polling loop may run for a screen that is not open.

## Success criteria

- **SC-001** A stream that raises a real connection error mid-flight delivers
  every sequence exactly once, in order, and presents the correct cursor on
  reconnect — asserted without a browser.
- **SC-002** A replaying source after reconnection is de-duplicated, asserted.
- **SC-003** A decision arriving as a run event closes the card, and the closed
  card offers no decision on any surface.
- **SC-004** An optimistic write refused by the server reverts and states why.
- **SC-005** A ten-thousand-event burst applies within budget, interaction
  responsive throughout.
- **SC-006** No subscription outlives its screen, asserted by a leak test across
  mount and unmount cycles.
- **SC-007** An end-to-end test drives a real run from start to completion in a
  browser against a real gateway.

## Out of scope

- The event stream itself, which the gateway already serves.
- The screens — feature 036.
- Autonomous behaviour that generates the events — features 039 and 041.
