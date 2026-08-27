# Tasks — 035 Console Live Layer

## Phase 1 — Reducer

- **T-001** Failing test: a source that raises a real connection error mid-flight
  yields every sequence exactly once, in order, and presents the correct cursor
  on reconnect.
- **T-002** Failing test: a source that replays already-seen events after
  reconnect is de-duplicated.
- **T-003** Failing test: out-of-order events are ordered before they are exposed.
- **T-004** Pure reducer implementing cursor tracking, ordering, de-duplication
  and idempotence per sequence, until T-001 to T-003 pass.
- **T-005** Terminal transitions: a run completing turns the live view into the
  completed view without a reload and without losing scroll position.

## Phase 2 — Transport

- **T-006** Server-sent event client presenting the cursor on connect.
- **T-007** Bounded backoff with visible connection state — connected,
  reconnecting, disconnected.
- **T-008** Failing test: a disconnected stream never renders as live.
- **T-009** Teardown on unmount; leak test across repeated mount and unmount.
- **T-010** A 401 mid-stream routes through the shell's single-collapse session
  path, asserted.
- **T-011** Background-tab throttling with full recovery on return.

## Phase 3 — Fan-out and cache

- **T-012** One subscription per run shared by all consumers; assert a page with
  three consumers opens one stream.
- **T-013** Reducer writes into the query cache; screens read from it.
- **T-014** Notification centre reads the same source; assert count and list
  cannot disagree.

## Phase 4 — Interaction

- **T-015** Agent question answerable in place; answering resumes the run.
- **T-016** Approval decidable in place; reason required on rejection.
- **T-017** Failing test: a decision arriving as a run event closes the card,
  names the decider, and the closed card offers no decision anywhere.
- **T-018** Takeover pausing at the next safe point, with resume and cancel.
- **T-019** Add-context to a running investigation without stopping it.
- **T-020** New-investigation drawer reachable from anywhere, without navigation.

## Phase 5 — Optimism

- **T-021** Failing test: an optimistic write refused by the server reverts and
  states the server's reason.
- **T-022** Mutation snapshots and rollback.
- **T-023** Confirmation naming target and consequence for irreversible actions.
- **T-024** Assert every toast-reported outcome is also present somewhere
  durable.

## Phase 6 — Live lists and budgets

- **T-025** Runs, approvals and incidents update in place; assert no reorder
  under the pointer.
- **T-026** Scroll anchoring with a "new events" control when scrolled up.
- **T-027** Benchmark: ten thousand events applied after reconnection within
  budget, interaction responsive throughout.
- **T-028** End-to-end browser test driving a real run from start to completion
  against a real gateway.

## Definition of done

- SC-001 through SC-007 each proven by a named test.
- The reducer is provable without a browser; only T-028 needs one.
- **Design fidelity.** The live states match `../_design/04-screen-incident.png`
  and the anatomy in [`../034-console-design-system/design.md`](../034-console-design-system/design.md):
  the connection-state indicator on the transcript header, the transcript event
  rail and icon wells, the bounded-payload row stating what it bounded and by
  what, the guardrail event rendered at danger weight, and the proposal card's
  decision row. Nothing introduced by this feature may change the resting layout
  of a screen feature 036 already built — a live view and a replayed view are the
  same component and must be indistinguishable except for the connection state.
- **Fidelity is judged against fixed data.** The comparison runs against
  feature 032's `populated` scenario — the same anonymised capture the mockups
  were drawn from — so a difference between console and mockup is a difference
  in the console and never in the data.
- **Divergence is allowed and must be recorded** in `deviations.md` with its
  reason, before the feature is called done.
- `make verify` green.
