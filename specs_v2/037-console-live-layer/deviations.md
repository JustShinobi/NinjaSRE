# Deviations — 037 Console Live Layer

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. Two routes were added to the gateway, because FR-012 had nothing behind it

**Documented.** FR-012: *"An operator MUST be able to take over a run, pausing
it at its next safe point, and to resume or cancel it."*

**What existed.** `POST /v1/investigations/{run_id}/cancel`, and nothing else.
`InvestigationRunner` — the protocol the REST surface steers a run through — had
`investigate`, `cancel`, `queue_message` and the three interaction methods. The
*platform* has the mechanism in full: `core/agent/react_loop.py` distinguishes
`pause` from `cancel` ("a paused run is `SUSPENDED` and resumable with its
evidence intact; a cancelled one is over"), and `core/agent/takeover.py` is a
whole model of a person driving a run and handing it back. What was missing was
the seam between that and the API.

**What shipped.** `take_over(run_id, *, principal)` and `resume(run_id)` on
`InvestigationRunner`, refusals for them on `UnconfiguredInvestigator`, and two
routes mirroring `cancel` exactly:

| Route | Permission | Why that one |
|---|---|---|
| `POST /v1/investigations/{run_id}/take-over` | `investigation.run` | Taking over is steering the run, which is the same authority as starting one and strictly more than reading it. |
| `POST /v1/investigations/{run_id}/resume` | `investigation.run` | Same. |

Both walk the same run → team → caller chain every other route on a run walks,
so a cross-team take-over is a 404 rather than a refusal that confirms the run
exists. `fixtures/contract/openapi.json` and `console/src/api/schema.ts` were
regenerated from the application, as their own drift checks require.

**The alternative was considered and rejected.** The console could have posted
"take over" to `/cancel`, whose docstring says "stop at its next safe point".
That would have made the one control an operator reaches for when they want to
*keep* an investigation the control that throws it away — the exact confusion
the platform's own `pause`/`cancel` split exists to prevent. Precedent: feature
021 §3 added the thin routes a rendering client could not work without, for the
same reason.

`test_console_live.py::test_every_run_action_the_console_posts_is_one_the_gateway_declares`
holds all four actions against `GATEWAY_ROUTES`, so a control that posts to a
route nothing serves fails the gate rather than failing in a browser.

## 2. The stream is read with `fetch`, not with `EventSource`

**Planned.** The technical-context table says "Server-sent events against the
gateway's existing run stream, with a cursor query parameter for catch-up". The
transport is server-sent events and the cursor is a query parameter — both hold.
What differs is the client: a `fetch` with a body reader rather than the
browser's `EventSource`.

Two reasons, and both are about honesty rather than convenience.

- **`EventSource` cannot present a cursor on the first connection.** It sends
  `Last-Event-ID` only on its *own* reconnections. A page reopened after a
  laptop slept would either start the transcript again from the beginning or
  begin wherever the deployment happened to be — and FR-002 is precisely that it
  does neither.
- **`EventSource` reports every failure as one opaque `error`.** A session that
  expired mid-stream would be indistinguishable from a network that dropped, so
  FR-007 (a 401 ends the session through the single-collapse path) could not be
  implemented at all: the console would sit reconnecting into a session that was
  over, showing a live badge above a transcript that had stopped.

`src/live/sse.ts` is the framing parser, pure and tested without a browser, and
`src/live/transport.ts` is the twenty lines that drive it. The chunk-boundary
case is asserted, because a parser that dropped its incomplete tail would lose
one event per chunk — silently, and more often the busier the run is.

## 3. `EventSource` also decided the shape of the courier

The credential is in an HTTP-only cookie, so a browser cannot present it to the
deployment. `src/app/api/stream/[runId]/route.ts` is therefore a third route
handler alongside feature 036's `decision` and `preview`, for the same
structural reason (their §9).

**It rewrites nothing.** The frames the browser reads are the frames the gateway
wrote, `id` included, because the cursor arithmetic belongs to the client and a
courier that renumbered events would be a second opinion about the order a run
happened in. `test_the_stream_courier_decides_nothing` asserts that the handler
contains no `JSON.parse`, no `sort(`, and no mention of `sequence`.

Two more handlers were added for the same reason: `src/app/api/run/` (start,
message, cancel, take-over, resume) and `src/app/api/answer/`. Both return the
deployment's own status and the deployment's own reason, which is what makes an
optimistic write revert *with a stated cause* rather than with one this console
invented.

## 4. A live run's transcript is seeded with nothing, not with the replay

The obvious design is: render the replay on the server, seed the reducer with
it, present that cursor, and let the stream fill the gap. It is wrong here, and
the reason is worth recording.

The two readers build **different identities** for the same event. A replayed
event's id comes from the turn and call it belongs to (`turn-0003-1-reasoning`);
a streamed event's comes from the run and the sequence (`run-0003-4`). Seeding
one with the other puts every event on the screen twice under two names.

So a run that has **settled** is read back through `Transcript` exactly as
feature 036 built it, and a run that has **not** is watched: the seed is empty
and the deployment's catch-up read — which is inclusive of the whole log — *is*
the transcript. One component either way, which is the rule that matters;
`test_the_live_view_and_the_replayed_view_are_still_one_component` asserts that
exactly one file in `src/` draws a transcript entry, and that the reducer builds
its events through the single mapping rather than its own.

## 5. The control panel is rendered only while there is something to steer

The definition of done says *"Nothing introduced by this feature may change the
resting layout of a screen feature 036 already built"*. A "Control" panel on
every completed run — even one showing an empty state — is a change to the
resting layout of `/runs/{id}`, which is a baselined screen.

So the takeover and add-context controls appear only when the run has not
settled. The fourteen non-gallery visual baselines are byte-identical after this
feature, which is the mechanical form of that requirement being met.

The cost is that a proof walking only `run-0001` would never see the live half,
so `tests/unit/support/screens.ts` gained a third detail screen — `run-0003`,
which is running in the committed dataset. Every cross-cutting proof (the role
matrix, the empty states, the accessibility audit) now walks the live screen as
well as the replayed one, and the three new write controls in the role matrix
are real assertions rather than vacuous ones.

## 6. Six gallery baselines were re-accepted, and nothing else moved

`src/design/status.ts` gained `CONNECTION_STATUSES` — five states, each with a
role *and* a shape. Not styled where they are shown: the design system's own
rule is that a screen needing something absent adds it to the library, and a
live indicator each screen coloured for itself is one that means something
slightly different on each of them. `disconnected` is **danger** rather than
neutral, deliberately: a transcript that has stopped updating is a transcript
somebody is about to draw a conclusion from.

The gallery renders every declared status, so the six gallery captures changed
and were re-accepted. The `Toast` entry changed too — see §7. No screen baseline
moved.

## 7. `Toast`'s dismiss label became a required prop

Feature 035 §5 left the sentences of primitives no surface rendered in place,
and said the rule's `files` list is where that gap closes — one entry at a time,
with the screen that first shows the string. This feature is the first thing to
render a toast, so `ToastProps.dismissLabel` is required, `src/live/**` and
`src/components/feedback.tsx` are in the untranslated-strings rule's file list,
and the gallery's danger toast gained the `recordedAt` it was missing (a toast
in the gallery with no durable record is the library documenting the thing the
design forbids).

## 8. Forty-one message keys were added, in both locales

`src/i18n/pt-BR.ts` is typed as partial on purpose so that the completeness test
can fail; it does not fail, because every new key was translated. The live
components take a `Locale` and call `message()` directly rather than being
handed a label bundle, the way `Topbar` and the palette already do: a "3 new
events" count is interpolated at the moment it changes, and a bundle resolved on
the server cannot carry a number that did not exist yet.

## 9. NFR-001's budget is on the reducer, not on the render

**Documented.** *"A burst of ten thousand events after a reconnection MUST be
applied within a declared budget without blocking interaction."*

`CONSOLE_LIVE_BURST_EVENTS` (10,000) and `CONSOLE_LIVE_BURST_BUDGET_MS` (750)
are declared in `config/constants/console.py` and read out of that file by the
test rather than restated. The budget measures `applyEvents`, and that is the
point: the reducer is pure, so this measures the thing that would make a tab
unresponsive if it were quadratic — and the burst is applied as **one batch**,
because the transport buffers frames into one before the reducer sees them.
Feature 036 already holds the *rendering* half: the transcript draws a hundred
entries whether there are a hundred or ten thousand.

The burst in the test arrives shuffled and with a five-hundred-event overlap,
because that is what a burst after a reconnection actually is.

## 10. Background-tab throttling is "no work", not "less work"

**Documented.** NFR-002: *"A background tab MUST reduce its work and MUST
recover fully on return."*

What shipped is stronger than reduction: while the tab is hidden, arriving
frames are buffered and **nothing is applied and nothing is rendered**, and a
reconnection that comes due is *owed* rather than scheduled — no timer runs for
a screen nobody is looking at, which is also NFR-004 read from the other end. On
return, everything that arrived is applied once, in order, and an owed
reconnection happens immediately.

## 11. SC-007's browser test drives a run to its last event, not to a terminal one

**Documented.** *"An end-to-end test drives a real run from start to completion
in a browser against a real gateway."*

The deterministic backing is the mock data plane serving the committed dataset,
and **that dataset's stream carries no terminal event**: `run-0003`'s recorded
stream ends at sequence 7 with a capability call, because it is a capture of a
run that was still going when it was taken. There is no honest way to assert a
completion against it, and inventing one would mean editing feature 032's
anonymised capture to make this feature's test pass.

So `tests/e2e/live.spec.ts` drives what is really there: a live run is watched
rather than read back, the connection state is on screen, the transcript fills
from the stream in sequence order, a *settled* run renders through the same
component with no stream at all, the drawer starts an investigation without
leaving the page, and stopping a run asks first and names it. The terminal
transition — including that the transcript's DOM node survives it, which is what
"without losing scroll position" means — is proved in the unit suite, where the
event can be delivered.

Also not asserted in a browser: the reconnection bound. Ten attempts at the
declared backoff is about forty seconds of wall clock, which is a browser test
nobody would run twice. It is asserted in the unit suite against injected time.

## 12. The one interval in the console is named rather than forbidden

NFR-004 says no polling loop may run for a screen that is not open.
`test_nothing_polls_for_data` asserts that exactly one file contains a
`setInterval` — `src/shell/browser.ts`, the wall clock behind relative
timestamps — and that it makes no request. Naming it in the test rather than
excluding it by a pattern means a second interval has to be argued for in that
file.

## 13. A defect the tests found, in code written for this feature

`RunConnection` scheduled its flush with `this.#cancelFlush = scheduler.after(0, …)`.
Against a scheduler that runs the callback **synchronously** — which the store's
own suite uses, and which is a perfectly legal implementation — the callback
cleared the field and then the assignment put a stale cancel handle back into
it. Every later event saw a non-null handle, declined to schedule a flush, and
was buffered for ever: **one event applied and the rest of the run silently
lost**.

Found by `store.test.ts` on its first run, not by reading. Fixed at both
scheduling sites with a flag the assignment is guarded on, and the guard is
commented with the failure it prevents.

## 14. Two lint rules shaped the code, and one of them for the better

`react-hooks/set-state-in-effect` rejected the first version of the scroll
anchoring, which counted new events by calling `setSeen(total)` inside the
effect that followed the viewport. The replacement is better rather than merely
compliant: the count is anchored in the *scroll handler* — the moment the
operator looked away — so the number is the difference from then rather than
from the last render, and the arrival of an event now changes no state but the
transcript's.

`@typescript-eslint/no-unnecessary-condition` rejected `if (this.#flushDue)` as
always-true because TypeScript does not track assignments made inside a
callback. The guard is a property on a small object instead, which the compiler
does re-widen after a call.

## 15. Task-by-task notes

- **T-005 (terminal transitions without losing scroll position).** Asserted as
  node identity: the test holds the `transcript` element before the terminal
  event and asserts the same node afterwards. A scroll offset in `jsdom` is
  always zero, so asserting on one would be a test that cannot fail.
- **T-010 (a 401 mid-stream).** Through `reportUnauthorized`, the same published
  refusal `src/lib/api.ts` uses, so three concurrent refusals still produce one
  prompt because there is one controller — not because the stream checked.
- **T-012 (three consumers, one stream).** Asserted with four, because the run
  detail has four: the transcript, the takeover panel, the interaction cards and
  the notification count.
- **T-014 (count and list cannot disagree).** By construction rather than by
  assertion: `attentionFrom` derives the list from the run's own events and the
  count is its length. The test drives two approvals and one decision through a
  real store and asserts the survivor.
- **T-022 (mutation snapshots and rollback).** `src/live/optimism.ts`, pure and
  outside React. A second attempt while one is in flight keeps the **original**
  snapshot: rolling back to a value that was itself never confirmed would put a
  fiction on the screen in place of a falsehood.
- **T-024 (every toast-reported outcome is also durable).** Enforced by the
  type — `Outcome.recordedAt` is required — and by `announce`, which throws on a
  blank one. There is no way to spell an outcome that exists only as a toast.
- **T-025 (lists update in place, no reorder under the pointer).** `src/live/lists.ts`
  is pure and takes "the pointer is over the list" as a parameter, because that
  is a fact only a component knows and a rule this module can then apply. A row
  already present is updated at the index it already holds; a new one is held
  back and counted.
- **T-027 (interaction responsive throughout).** The scaling claim rather than a
  responsiveness probe: the burst is one pass through the reducer and one
  render, and the transcript's entry count does not depend on the event count.
  A main-thread responsiveness measurement in `jsdom` would measure `jsdom`.

## 16. What is rendered but not yet reachable from every screen

`FR-013` (add context) and `FR-012` (takeover) are on the run detail, which is
where the run is. They are not on the incident detail, which also shows a run:
that screen's transcript is feature 036's and the incident's own live half
belongs with the work that gives an incident a stream of its own.

The new-investigation drawer *is* reachable from everywhere — it is in the
shell, opened by the utility bar's primary action, and the browser test asserts
that opening it does not change the address.

## 17. A flake seen once, and what was done about it

`tests/e2e/budgets.spec.ts` — feature 035's route-transition budget — failed
once on a machine that was simultaneously running a type check, and passed on
the two runs after it. Nothing in this feature touches it, and it is a wall-clock
assertion on a loaded runner. Recorded rather than fixed: if it recurs it is a
budget to re-derive rather than a test to relax, and `make console-e2e-sweep`
exists for exactly that argument.

Also worth naming: the console's server logs `Error: The destination stream
closed early` whenever a browser navigates away from a page holding an open
stream. That is the courier's upstream `fetch` being aborted with the request,
which is correct behaviour — the alternative is a stream nobody reads staying
open on the deployment — but it is noise in the browser suite's output.

## 18. Test-first sequencing

Followed per module, for the reason every feature since 020 gives: a suite
written against modules that do not exist can only fail on `ImportError`, which
proves nothing.

`reducer.test.ts` was written and confirmed red against a missing
`src/live/cursor.ts`, then made green by the reducer. `connection.test.ts` was
written before the transport and is what fixed the shape of `StreamSource`,
`Scheduler` and `Visibility` — all three are injected because the test needed
them to be, which is the argument for writing it first. The gateway's two new
routes had their tests written and watched failing (404) before the protocol
methods existed. `store.test.ts` found the defect in §13 on its first run.

The contract test was written last, which is the right order for it: a map from
each criterion to a named proof is only worth as much as the proofs in it.

## 19. Gate

`make verify` green: **9,865 passed, 20 skipped** in 5m16s — ruff, format, mypy
strict over 1,433 files, the seven import contracts, every guard check including
the console boundary, and the console half in full: the lockfile, format, lint
(the design-literal rule and the untranslated-string rule, now over `src/live/**`
and `src/components/feedback.tsx`), types, **962 unit tests** at 95.7%
statements / 90.6% branches against a floor of 90, the API client drift check,
the standalone production build, both bundle budgets, **60 browser tests**
against the committed dataset, and **twenty visual comparisons** inside the
pinned image.

Of the Python total, 33 are this feature's own contract tests in
`tests/contract/console/test_console_live.py` — including the map from each
success criterion to the named test that proves it, so a proof that is deleted
or renamed fails there. The working tree is clean afterwards.
