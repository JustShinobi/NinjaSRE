# Deviations — 036 Console Data Surfaces

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. Two areas exist that the twelve-area manifest did not have

FR-020 (the capability catalogue) and FR-023 (administration: principals,
grants, tokens, SSO) name whole screens, and feature 035's manifest has no area
for either. Both are now areas:

| Area | Path | Group | Permission | Why that permission |
|---|---|---|---|---|
| Catalogue | `/catalogue` | Learn | `investigation.read` | The gateway requires it on `GET /v1/capabilities`. |
| Administration | `/administration` | Govern | `identity.read` | The gateway requires it on `GET /identity/principals`. |

Both rows are held against the gateway's own route table by
`test_console_surfaces.py::test_a_new_area_takes_the_permission_the_gateway_requires`,
so neither is a permission somebody chose.

**Catalogue is in *Learn* rather than in *Govern*, and that is a decision rather
than a filing accident.** What the deployment *can do* belongs beside what it
knows. It also has a mechanical consequence worth stating: the catalogue takes
`investigation.read`, which every role holds, so putting it under Govern would
have shown a "Govern" group to a viewer who can reach nothing else in it — and
`tests/unit/shell/routes.test.ts` asserts that an empty group is dropped
entirely, which is the same rule read from the other end.

Integration configuration (FR-021, FR-022) is a panel of the catalogue rather
than an area of its own, gated on `integration.manage`. It is the same subject as
"what can this deployment do", read from the other side.

## 2. The console reads eight endpoints the API document does not declare

The estate inventory and continuous observation are separate pieces of work.
Their shapes are decided — the mock data plane serves them and its catalogue is
the authority — but nothing has generated them into `src/api/schema.ts`, so
`read()` cannot name them and should not be made to.

`src/lib/api.ts` therefore carries `PROJECTED_PATHS`: a **closed, enumerated**
list, read through `readProjected`, which returns `unknown` so that every reader
has to say what it expects. Three properties keep it honest, all asserted in
`tests/contract/console/test_console_surfaces.py`:

- every path in it is one the mock plane projects, so the console cannot invent
  an endpoint;
- **no path in it is one the gateway already serves** — the list has to shrink,
  and the test fails on the day an endpoint lands and nobody moved it;
- the fixture server answers every one of them, so a screen reading a projected
  path is a screen the unit suite and the visual capture can both fill.

A 404 from a projected path becomes *empty* rather than *error*, because a
deployment nobody has connected anything to is new rather than broken. Every
other refusal stays an error.

## 3. `read()` learned to bind a path's variables, because it could not

Feature 035's client interpolated nothing: `read('/v1/runs')` worked because the
shell only ever read collections. `read('/v1/runs/{run_id}')` would have
requested `/v1/runs/%7Brun_id%7D` and come back 404 — which reads on a screen as
"there is no such run", the one message that would send somebody looking in
exactly the wrong place.

`ReadOptions` now carries `params` and `query`. A missing variable **throws**
rather than sending the brace, and `tests/unit/surfaces/behaviour.test.ts`
asserts both the binding and the refusal.

## 4. FR-005 asks the run list for two columns the run list's payload has not got

**Documented.** "The run list MUST show status, trigger, subject, team, duration,
cost and attention state."

**`GET /v1/runs` carries** `run_id`, `status`, `trigger`, `summary`,
`started_at`, `finished_at`. There is no team and no cost on a run record; cost
is on the *replay*, which is one read per run.

**What shipped** is every column the payload supports — run, status, trigger,
subject, started, duration — with duration computed from the two instants. Cost
is on the run detail, broken down by model and by turn, which is where FR-009
asks for it and where the data actually is.

**Attention state is carried by the status column's semantic role** rather than
by a column of its own: `failed` is danger, `awaiting_approval` is warning, and
both are drawn with a shape as well as a colour. A separate "attention" column
holding a second copy of that judgement is a column that disagrees with the
status beside it the first time somebody adds a state.

Reading the replay per row was considered and rejected: it is N+1 against a list
whose whole non-functional requirement is ten thousand rows.

## 5. Three panels have no endpoint behind them, and say so rather than being absent

| Panel | Screen | What it says |
|---|---|---|
| Strategies with their anti-patterns (FR-012) | Memory | what a strategy is, and that enough episodes have to agree before one is synthesised |
| The agent-proposal review queue (FR-013) | Knowledge | what a proposal is and where it comes from |
| The rules table (design.md, Autonomy) | Autonomy | that the absence of a rule resolves to propose-only |

None of the three has a gateway endpoint or a projected fixture. The alternative
to an empty state naming the next action was to leave the region out, and that is
the failure this whole feature exists to prevent: a screen that shows six of its
seven regions is a screen whose seventh looks like something that broke.

The autonomy one is the one that matters. **A permanent footer states that the
absence of a rule resolves to propose-only**, on the page, always, next to an
empty rules table — because an operator reading an empty table has to know
whether empty means "anything goes" or "nothing happens without me", and guessing
the permissive answer is the one direction this must never be wrong in.

Not shipped at all: the design's **"Effectiveness here"** rail on the incident
detail — how each candidate remediation has performed on *this* resource
historically. Nothing records per-resource remediation effectiveness, in the
gateway or in the projection, so there is no honest empty state for it either:
the sentence would have to be "this would say how well each fix has worked, if
anything counted", which is a promise rather than a next action. It belongs with
the work that starts counting.

## 6. Twenty-three statuses were added to the design system

`src/design/status.ts` knew run statuses and resource health. The data surfaces
put severities, incident states, decision states and side-effect levels in chips,
and every one of them was rendering as an unknown word — which is to say, in
grey. A `critical` severity drawn in grey is the one colour it must not be.

`ATTENTION_STATUSES` declares them, `DECLARED` maps each to a role *and* a shape,
and the gallery renders all of them. `critical` and `high` are both danger and
carry different shapes, which is the reason a shape is carried at all.

`awaiting_approval` is in this group rather than in `RUN_STATUSES`: the gateway
reports it on a run, but it is a fact about an interaction. Adding it to the run
list would have changed what feature 034's `isRunStatus` means.

## 7. One icon was added, and the areas' icons come from the existing set

`UsersIcon`, for administration, on the same 24-unit grid at the same 2-unit
stroke. The icon budget is 16,384 bytes and the set is at 10,832 after it.
Catalogue reuses `LayersIcon`; the eleven transcript event kinds and the six
activity kinds are all drawn from icons that already existed, which is why a
feature with seventeen new visual categories added one glyph.

## 8. The empty-state action is a link, and `Panel` is not `Card`

`EmptyState` takes a callback. Every empty state in this feature is "go and do
the thing that produces this data", which is a navigation — so `Panel` wires the
callback to `window.location.assign` and renders an `sr-only` anchor beside it
with the same destination, exactly as `src/shell/empty-link.tsx` established for
the not-found page. Anything that reads a page for its outbound edges finds a
real link.

`Panel` renders its own chrome rather than composing `Card`. They are different
things: a card is a titled container, and a panel is a region with a boundary, a
scoped retry and three *required* state declarations. Composing them would have
meant either passing `state="ready"` to `Card` always — leaving its `data-state`
attribute lying — or lifting `Card`'s three one-line state messages into required
props for the benefit of a component that never renders them.

## 9. Two console route handlers exist that the plan does not mention

`src/app/api/decision/` and `src/app/api/preview/`.

Both exist for the same structural reason as `src/app/api/session/`: the
credential is in an HTTP-only cookie, so a browser cannot present it, and a
decision or a preview made on a screen has to pass through the console's own
process. **Neither decides anything.** The preview forwards the patch and returns
the deployment's body verbatim — `test_the_preview_handler_forwards_rather_than_deciding`
asserts the verbatim return, and `test_the_console_holds_no_configuration_merge`
asserts there is no merge anywhere in `src/` for it to have used instead.

The decision handler refuses exactly one thing on its own account: a rejection
with no reason. The control on the screen refuses one too, and that is not
duplication — the control is a courtesy to the person using it and the handler is
the rule.

## 10. Every page resolves its own viewer, and the layout still resolves one

`src/app/(shell)/layout.tsx` resolves the viewer for the frame. `surfaceContext`
resolves it again for the page. That is deliberate rather than an oversight: a
client-side route transition fetches the **page** segment without re-rendering
the layout, so a page that relied on the layout having resolved a viewer would
render with nobody's permissions on exactly the navigations people make most.

`cache()` from React collapses the two reads into one whenever they do happen in
the same render, which is every full page load.

## 11. `RowList` is windowed but not paginated, and `Transcript` is paged but not windowed

FR-025 says "paginated or virtualised, never truncated silently", and the two
components take the two different answers because they are two different shapes
of problem.

A **row** is fixed height by contract, so its position is arithmetic and a window
is exact: ten thousand rows put the same number of elements in the document as a
hundred, and the scrollbar means what it says because the space is reserved.

A **transcript entry** is not fixed height — it holds a payload — so windowing it
would need measurement, and measuring ten thousand entries to place one is the
cost the requirement exists to avoid. So the transcript draws a hundred at a
time, says which hundred of how many, and moves in both directions. It opens on
the *most recent* hundred, because that is what somebody came for.

Neither truncates: both say how many there are.

## 12. Sorting is a link and filtering is a navigation

Not stated in the tasks, and worth recording because it is what makes SC-007 true
by construction rather than by discipline. A column header is an anchor carrying
the address the sorted view has; a filter pushes a new address. There is no code
path in this feature that changes what a list shows without changing the address,
which is a stronger claim than "the filters are also written to the URL".

The side effect is that sorting works with JavaScript disabled.

## 13. The fixture server now serves thirty-five endpoints, not four

Feature 035's `scripts/fixture-server.mjs` answered the four reads the *frame*
makes. Every screen in this feature reads more than that, and a visual capture of
a page of error states says nothing about the design.

It now carries the full read surface with `{variable}` templates and picks the
recorded response whose arguments match. Three consequences:

- the **unit suite imports the same module**, so a screen tested in `jsdom` and a
  screen photographed in a browser are looking at one dataset — the `populated`
  scenario, which is the same anonymised capture the mockups were drawn from,
  which is what the definition of done means by "fidelity is judged against fixed
  data";
- it is still not a second mock data plane: it does not validate, does not write,
  and answers reads alone. The behaviour suite still runs against the real one;
- its table is held against the mock plane's catalogue by two Python tests, one
  of which is feature 035's and unchanged.

`scripts/fixture-server.d.mts` declares its types, because `allowJs` is off and a
JavaScript module the compiler silently types as `any` is a module the gate has
nothing to say about.

## 14. Feature 035's route-file test now renders real screens

`tests/unit/shell/route-files.test.tsx` rendered twelve pages that made no
requests. Its pages now read, so it signs in (a cookie) and serves the committed
dataset. What it proves is unchanged and slightly stronger: every route file
renders cold, with its own title, against real data.

`tests/unit/setup.ts` gained a floor mock of `next/navigation`. `useRouter`
asserts that the App Router is mounted, which it is not in a bare `jsdom` render,
so without it every test that renders a panel would fail on the frame rather than
on what it is testing. A file that is *about* the navigation declares its own
mock and that one wins.

## 15. `placeNodes` had a defect the test found

A configuration tree whose parent chain contains a cycle produced **no nodes at
all**: nothing was a root, so the walk had nothing to start from. Every node is
now appended at the root if the walk could not reach it. A malformed tree is a
thing an operator can go and fix; a tree that renders as empty is a thing they
conclude the console cannot show.

## 15a. The visual capture needed a fixed clock, and the baselines said so

The first accepted baselines failed an hour later. The committed dataset carries
one fixed instant — that is feature 032's whole design, and it is why two
captures a week apart used to produce identical images — but a screen rendering
"17 hours ago" reads that instant against the **console's** clock, and an hour
later it says eighteen.

`NINJASRE_CONSOLE_CLOCK` is declared in `config/constants/console.py`, read in
`src/surfaces/context.ts` and nowhere else, and set by `scripts/visual.mjs` to
the instant it reads out of the dataset's own `captured_at` — read rather than
written down, so a recapture of the fixtures moves the console's clock with them.
Unset in a deployment, where the clock is the right answer. An unparseable value
falls back to the clock rather than to 1970, which would render every timestamp
as "56 years ago" and look like a data fault.

`test_the_console_and_this_tier_agree_about_the_fixed_clock` holds the name in
both files and asserts the capture sets it.

## 15b. The resources list says *state*, not *health*

The design draws a health badge — HEALTHY, DEGRADED, UNHEALTHY, STALE. The
projected inventory reports a **lifecycle** state on that field: `running` and
`stopped`, nothing else. Labelling that column "Health" would have put the word
RUNNING under it, which is a screen that reads as if the console does not know
what health is.

So the column is **State**, the filter with it is **State**, and the sort order
names both vocabularies so it keeps working when the field starts carrying a
verdict. The derived verdict is on the resource *detail* as the named checks it
came from — the same "why degraded" panel the incident detail shows, which is the
one the definition of done calls non-negotiable and which is there.

Deriving a per-resource verdict here from those checks was the obvious
alternative and is the thing `plan.md` forbids: exactly one thing derives health,
and it is not this.

## 15c. The shared test modules moved out of `tests/unit/surfaces/`

`make check-console-boundary` rejects a console file naming `../surfaces/…`,
because `surfaces/` is a Python tier. The guard matches the text of a relative
import rather than resolving it, and `tests/unit/shell/route-files.test.tsx`
importing `../surfaces/support` is a console file reading another console file.

The guard is right to be blunt and was not touched. The two shared modules are
`tests/unit/support/dataset.ts` and `tests/unit/support/screens.ts` instead,
beside the accessibility audit that already lives there.

## 16. Fidelity: where the screens differ from the references

Reviewed side by side at 1440 against the `populated` scenario, as the definition
of done requires. Everything the definition enumerates non-negotiably holds: the
attention block is above the statistics, the proposal card carries all eight
documented fields in the documented order, the "why degraded" panel shows named
signals and their values with a note that the raw provider status is retained,
and every empty state carries an icon, a heading, a sentence and an action.

What differs:

- **The figures are not the mockup's four.** The reference draws *Resources
  watched · Healthy · Degraded and unhealthy · Mean time to detect*. Nothing
  records a time to detect — there is no detection instant on any endpoint or any
  projection — and FR-003 forbids a figure with no drill-down, which a fabricated
  one would also have. The fourth tile is **Runs in the last day**, with the
  failed count as its comparison and the run list behind it.
- **The comparison lines are counts rather than deltas.** "0 of 86 at the last
  sweep", not "↓ 4 since yesterday". A previous-period comparison needs a
  previous period, and the estate summary is one instant. The tile still carries
  a period and a breakdown, which is the half of FR-003 the data supports; the
  arrow arrives when something records history.
- **The attention block shows twelve rows against the mockup's three**, because
  the `populated` dataset has twelve things waiting. The mechanism is the same and
  the numbers are the fixtures'.
- **The activity feed mixes incidents and runs only.** The design names five
  kinds — incidents, verifications, recurrences, sweeps, guardian events. Two of
  them have data. `ActivityFeed` declares all six kinds with an icon each, so the
  three that are missing are a data question rather than a component change.
- **The guardian card states liveness, posture and the live detector count, and
  not the freeze window or the heartbeat age.** Neither is served. Liveness and
  posture are the two the design calls out as load-bearing, and both are there.
- **The resources screen has no segmented "All · Problems · Guests · Storage ·
  Nodes" control.** It has a kind filter and a state filter, both in the address,
  which is the same reachable set through the mechanism every other list here
  uses. A second filtering idiom on one screen is the thing the design system
  exists to prevent.
- **Its health column is a state column.** See §15b.
- **The estate health card lists counts by kind rather than a per-datastore
  meter list.** `GET /v1/estate/summary` carries `by_kind`; the per-resource
  utilisation the mockup's bars show is on `/v1/estate/resources`, and reading the
  whole inventory to draw five bars on the overview is the read this panel should
  not make.
- **The incident detail's proposal card is reviewed on the approvals capture.**
  The reference draws the card inside an incident; in the `populated` dataset the
  two pending proposals are not attached to an incident, so the card is where the
  proposals are.

`04-screen-incident.png`, `05-screen-estate.png` and `06-screen-autonomy.png`
moved from `pending` to `baselined`, and `03-screen-dashboard.png`'s note now
says its panels are reviewed here rather than deferred.

## 17. Nine visual baselines were added, and four were re-accepted

New: `runs-1440-light`, `run-detail-1440-light`, `run-detail-1440-dark`,
`incident-1440-light`, `approvals-1440-light`, `resources-1440-light`,
`autonomy-1440-light`, `configuration-1440-light`, `resources-320-light`.

Re-accepted: the four `shell-*` captures, because `/` is the overview and the
overview now has content in it. Their acceptance records already said the panels
inside the frame would be reviewed when the data surfaces landed; this is that.

## 18. Test-first sequencing

Followed per module, for the reason every feature since 020 gives: a suite
written against modules that do not exist can only fail on `ImportError`, which
proves nothing.

`panel.test.tsx` was written and confirmed red against a missing
`src/surfaces/panel.tsx`. `window.test.ts` and `rows.test.tsx` were written
before the window arithmetic and stayed red against real defects — `rows.tsx`
called `scrollTo` on an element `jsdom` has no `scrollTo` for. The transcript
benchmark was written before the component and is the reason the component is
paged rather than complete. `tree.test.tsx` was written before `placeNodes` and
found the cycle defect in §15.

The cross-cutting proofs were written last, which is the right order for them:
each walks a list of screens, and a list of screens is only worth as much as the
screens in it.

## 19. Task-by-task notes

- **T-003 (a panel with no declared empty state fails the suite).** Enforced by
  the type rather than by a test: `PanelProps.empty` is required and
  `EmptyState` throws on a blank body or a blank action label. There is no way to
  spell a panel without one, which is stronger than a test that catches one.
- **T-005 (benchmark on ten thousand rows).** A *scaling* assertion rather than a
  stopwatch: the number of rows in the document is the same for a hundred, ten
  thousand and a million. A wall-clock number measured on a loaded CI runner is a
  flake waiting for a busy afternoon.
- **T-007 (transcript benchmark).** Both — the scaling claim and a stopwatch
  against `CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS`, which is declared in
  `config/constants/console.py` and read out of that file rather than restated.
  Same for `CONSOLE_CONFIG_TREE_RENDER_BUDGET_MS` and T-020.
- **T-016 (episode filters).** The component filter is passed to the *server*,
  because `/v1/memory/search` takes one and a console that read the whole corpus
  to filter it in a browser stops working at the size the corpus becomes worth
  having. The outcome filter is applied to what came back, because the endpoint
  does not take one.
- **T-019 (a two-hundred-dependent case).** The graph draws twelve per side and
  says how many there are; the list beside it has every one. The list is not a
  fallback — it is the complete view, and it is the one a keyboard walks.
- **T-024 (decide in place).** Through the interaction the approval belongs to,
  which means one extra read per pending run: the API addresses a decision by
  interaction rather than by approval, and a console that guessed the identifier
  would be a console that decided the wrong thing exactly once.
- **T-025 (audit export).** A link to the API's own `/audit/export`, carrying the
  same filters, gated on `audit.export`. Not a CSV assembled in the browser: a
  record the console reformatted is a record whose provenance is the console.
- **T-029 (SSO configuration).** A panel that names it and points at where it
  will be configured. Nothing serves SSO settings, and a form that posted nowhere
  would be worse than a sentence.
- **T-033 (visual baselines at three widths in both themes).** Nine screens
  rather than the full cross product. Six captures per screen × fifteen screens is
  ninety images through one pinned container on every run, and the browser suite
  already asserts the stronger responsive claims — nothing overflows at 320, and
  every box is identical between the two themes. The widths and themes that catch
  something are captured: 320 for the densest table, dark for the densest screen.

## 20. Things added that the tasks do not ask for

- **`tests/unit/surfaces/support.ts` and `pages.ts`.** One list of screens and
  one way to serve the dataset, shared by five test files. Every cross-cutting
  proof is "for every screen …", and a per-screen assertion written by hand is one
  that stops being written by about the ninth screen.
- **`ATTENTION_STATUSES`.** See §6.
- **`type="password"` on `Input`.** A credential typed in plain sight is a
  credential the person at the next desk has read.
- **`src/surfaces/` added to the untranslated-strings lint rule.** Feature 035's
  deviation §5 left the primitives' own sentences in place until a screen showed
  them, and said the rule's `files` list is where that gap closes. It closes for
  the surfaces here; the primitives this feature does not render still carry
  theirs.

## 21. Gate

`make verify` green: **9,829 passed, 20 skipped** in 4m58s — lint, format, mypy,
the seven import contracts, every guard check including the console boundary, and
the console half in full: the lockfile, format, lint (the design-literal rule and
the untranslated-string rule, now over `src/surfaces/**`), types, **839 unit
tests** at 96.0% statements / 90.5% branches against a floor of 90, the API
client drift check, the standalone production build, both bundle budgets, **55
browser tests** against the committed dataset, and **twenty visual comparisons**
inside the pinned image.

Of the Python total, 25 are this feature's own contract tests in
`tests/contract/console/test_console_surfaces.py` — including a map from each
success criterion to the named test that proves it, so a proof that is deleted or
renamed fails there. The working tree is clean afterwards.
