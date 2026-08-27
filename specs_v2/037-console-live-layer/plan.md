# Plan — 035 Console Live Layer

## Technical context

| Concern | Choice |
|---|---|
| Transport | Server-sent events against the gateway's existing run stream, with a cursor query parameter for catch-up |
| Reducer | A pure event reducer, separate from React, unit-tested without a DOM |
| Cache | The query layer's cache is the single store; the reducer writes into it, screens read from it |
| Optimism | Mutations apply to the cache immediately with a rollback snapshot |
| Fan-out | One subscription per run, shared by every component on the page |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | A live transcript must not imply freshness it does not have. | FR-005: a disconnected stream never presents as live. The connection state is always visible. |
| II — Bounded autonomy | Takeover and pause are operator controls over an autonomous run. | Pause happens at the runtime's next safe point, never mid-call, which is the runtime's existing contract. |
| VIII — Layered architecture | The console consumes events; it does not produce or interpret them. | The reducer maps event kinds to view state. It derives no domain conclusion. |
| XII — Test-first | Exactly-once across reconnection is the property most likely to regress. | The reducer is pure so this is a unit test, and it lands before the transport. |

## Architecture decisions

**The reducer is pure and lives outside React.** Exactly-once delivery across a
reconnection is the hardest property here and the easiest to break. Keeping the
reducer a pure function of (state, event) means it is provable in a unit test
with a fake source that raises mid-flight — no browser, no timing, no flake. The
first wave established this seam in `live.py`; it carries over directly.

**One subscription per run, shared.** A page with a transcript, a cost panel and
an approval card is three consumers of one stream. Three subscriptions would
triple the server's fan-out and would let the three disagree about what has
arrived.

**Cursor first, then events.** On every connect the client presents the last
sequence it applied. The server fills the gap. The client discards anything at or
below its cursor. This makes duplicates harmless by construction rather than by
the server promising not to send them.

**Optimistic writes keep a rollback snapshot.** Every mutation records the state
it replaced. A refusal restores it and states the server's reason. Without the
snapshot, a refused optimistic write leaves the UI asserting something false,
which is worse than not being optimistic at all.

**A toast is never the record.** Every outcome a toast announces also lands
somewhere durable — the run's transcript, the audit view, the notification
centre. Toasts are dismissible and easy to miss, and an operator who missed one
must still be able to find out what happened.

## Phases

1. **Reducer.** Pure event application, cursor tracking, ordering,
   de-duplication, terminal transitions. Unit-tested against a source that
   raises, replays and reorders.
2. **Transport.** Server-sent events, bounded backoff, visible connection state,
   teardown on unmount, session collapse on 401, background-tab throttling.
3. **Fan-out and cache.** One subscription per run; reducer writes into the query
   cache; screens read from it; notification centre reads the same source.
4. **Interaction.** In-place answers, approvals with required rejection reason,
   takeover and resume, add-context, the new-investigation drawer.
5. **Optimism.** Mutation snapshots, immediate application, rollback with a
   stated reason, confirmation for irreversible actions.
6. **Live lists.** Runs, approvals and incidents updating in place without
   reordering under the pointer; scroll anchoring with a new-events control.

## Risks

- **Reconnection correctness is easy to assert and hard to achieve.** Mitigated
  by testing the reducer against an adversarial source — one that drops, replays,
  reorders and duplicates — before any real transport exists.
- **Optimism plus streaming can double-apply.** Mitigated by making the reducer
  idempotent per sequence, and by having optimistic writes carry the same
  identity the resulting event will, so the event supersedes the optimism rather
  than adding to it.
