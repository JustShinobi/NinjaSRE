# Deviations — 035 Console Application Shell

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. FR-007 and the plan's own session design contradict each other

**Documented.** FR-007: *"The credential form MUST post to the API origin, never
to the console origin."* `plan.md`'s technical-context table: *"Token exchanged
for an HTTP-only cookie by a console route handler; the browser never holds the
token in readable storage."*

**These cannot both be literally true.** A cross-origin form post cannot set a
first-party HTTP-only cookie on the console's origin — the response comes from
the API and the browser will not let it write a cookie for somebody else. One of
the two sentences has to give.

**What shipped is the plan's design, and the property FR-007 is actually about.**
The form posts to `/api/session`, a console route handler, which:

- offers the credential to the **API origin** (`GET /auth/me` with the bearer
  token) and believes the answer — the console never decides whether a
  credential is good, which is the "one implementation" rule the plan's
  constitution check names;
- keeps it in an HTTP-only, `SameSite=Strict` cookie, so `document.cookie` and
  `localStorage` cannot reach it however hard a component tries;
- never puts it in a URL, a response body, or a log;
- redirects with **303** rather than 307, because a 307 replays the POST and the
  body of that POST is the credential.

`tests/unit/shell/session-route.test.tsx` asserts each of those four as a
separate test, including the two that are about places the credential must *not*
be. FR-007's underlying requirement — "MUST never place a secret in a URL, a
log, or client storage readable by another origin" — is satisfied in full. The
clause about the form's `action` is not, and could not be.

Feature 021's SC-006 (the *integration* credential form posting to the API
origin) is untouched and still holds; that form is a different thing and is
still asserted by `test_console_is_an_api_client.py`.

## 2. `/` is the overview now, and the run list moved to `/runs`

Feature 033 shipped `src/app/page.tsx` as a run list, explicitly so the gate had
a real page to prove itself against, and its own screen registry said the screen
"is expected to be replaced rather than restyled". This feature replaces it: `/`
is the dashboard the design draws, and `/runs` is one of the twelve areas.

Deleted with it: `tests/unit/page.test.tsx`, `tests/e2e/runs.spec.ts`, and the
`runs` visual baseline. What they proved — that the built artefact serves, that a
server component's fetch reaches the configured address, and that what comes back
is rendered into a real document — is now proved by `tests/e2e/shell.spec.ts`
against twelve routes instead of one.

## 3. The twelve areas render a frame and a sentence, not a screen

`spec.md` puts the content of the pages out of scope ("feature 036"). So each of
the twelve renders the page header — icon, title, context, breadcrumb where the
route is nested — and one line saying the surface arrives with the data screens.

Stated rather than left implied: **that line is the whole body of eleven of the
twelve pages today.** An empty rectangle would be indistinguishable from a page
that failed to load, which is the one thing a shell must never look like.

## 4. Four areas take a permission no gateway route declares yet

The manifest's rule is that each area takes the permission the gateway requires
on the data it reads, and `test_console_shell.py` holds eight of the twelve
against the gateway's own route table. The other four have no gateway row,
because the endpoints behind them are the *projected* half of feature 032's
dataset:

| Area | Takes | Why |
|---|---|---|
| Incidents | `investigation.read` | An incident is what an investigation is opened on, and the run list beside it already takes this. |
| Resources | `investigation.read` | The estate inventory is observed state read by the same reader. |
| Detectors | `config.read` | A detector is configuration of what is watched for. |
| Autonomy | `config.write` | **The one deliberate narrowing.** The screen exists to *change* what the deployment may do on its own. A reader who cannot change it already sees the current posture on the overview and in the sidebar footer, which is on screen on every page. |

All four are held to the platform's catalogue by
`test_every_declared_permission_is_one_the_platform_has`, so none of them can be
a permission somebody invented. `AREA_ROUTE` in that module gains a row for each
as the endpoint serving it lands.

`test_the_role_matrix_can_tell_two_roles_apart` exists because of this table: it
asserts the least privileged role reaches strictly fewer areas than the most,
which is what stops SC-003 passing vacuously against a manifest where everything
needs the same permission.

## 5. The i18n lint rule covers the surfaces, not every primitive

**Planned.** T-022: *"add a lint rule rejecting string literals in components"*.
FR-015: *"No string literal in a component."*

**Done.** `eslint-rules/no-untranslated-strings.mjs` rejects literal text in the
tree and literal sentences in the ten attributes a person reads or hears. It runs
over `src/app/**`, `src/shell/**`, `src/session/**`, `src/i18n/**`, and three
design-system modules.

**Every primitive the shell renders had its strings lifted to required props**,
because those sentences are on a screen somebody reads:

| Primitive | Was | Now |
|---|---|---|
| `Breadcrumb` | `aria-label="Breadcrumb"` | required `label` |
| `Avatar` | `"Unknown person"` | required `unknownLabel` |
| `Pagination` | `Previous` / `Next` / `Page N of M` | required `labels` |
| `Overlay` / `Modal` / `Drawer` / `ConfirmDestructive` | `label="Close"`, `Cancel`, "This will change" | required `closeLabel`, `labels` |
| `ErrorState` | three sentences | required `heading`, `retryLabel`, and the whole body via `detail` |

**The primitives no surface renders kept theirs, and this is the gap.** `Button`'s "(destructive)",
`Link`'s "(opens in a new tab)", `Timeline`'s "side effect", `CodeBlock` and
`DiffView`'s bound notices, `Toast`'s "Dismiss this message", `Combobox`'s "No
match for …", `DateRange`'s "The range ends before it starts.", `StatTile`'s
"Loading", and `Timeline`'s default empty line.

**Why they were left.** No surface in this feature renders any of them, so none
of those sentences is on a screen anybody can read in the wrong language. Making
them required props would change a delivered API from the previous feature, with
no screen behind the change to review it against, and would rewrite roughly
fifteen assertions in that feature's suite for a string nobody is currently
shown. Feature 036 puts each of these on a screen for the first time, and closing
this gap belongs with the screen that first shows it: the rule's `files` list is
where that happens, one entry at a time, and each addition fails loudly until the
strings are lifted.

`console/fixtures/untranslated-literal.tsx` is spliced into `src/shell/` by
`test_console_gate.py` and the lint step is required to reject it by name, so the
rule has been watched failing rather than assumed to work.

## 6. The visual capture now serves the real dataset, which it could not before

Feature 033's capture harness pointed the console at `http://127.0.0.1:9` — a
port nothing listens on — and intercepted requests **in the browser**. That works
for a page whose data is fetched by the browser. It does not work for this
feature: the shell resolves the viewer on the *server*, and a console with
nothing to talk to captures the sign-in page for every screen.

So `scripts/fixture-server.mjs` serves the committed `populated` dataset over
loopback, in Node, inside the same capture container. The dataset carries one
fixed instant, so two runs a week apart produce identical images — which is the
property the interception was there to protect and which this keeps.

Consequences worth naming:

- The browser interception is gone from `tests/visual/screens.spec.ts`; there is
  one source of data now rather than two.
- The visual suite signs in (a cookie, not the form) for every screen but the
  sign-in itself, because the guard is above the router and would otherwise
  redirect all of them.
- The fixture server's endpoint table is four rows. It is not a second mock data
  plane; the behaviour suite still runs against the real one.
  `test_the_fixture_server_answers_endpoints_the_dataset_actually_has` holds its
  four rows against `tools/mockplane/endpoints.py`, so it cannot drift.

## 7. Fidelity: where the shell differs from `03-screen-dashboard.png`

Reviewed side by side at 1440 against the `populated` scenario, as the definition
of done requires. Everything the definition enumerates matches: the sidebar is
236px, the four groups are Operate · Estate · Learn · Govern in that order with
an icon and a label each and the current one marked, the topbar is 52px and
carries the palette, the theme switch, the notification centre and the account
menu, the page header is icon-title-context, and the sidebar footer states
guardian liveness and posture. What differs:

- **The utility bar carries the deployment name and the mockup's does not.**
  FR-011 requires it. The mockup puts the deployment in the *page header*
  ("Cluster HAL9000"), which is the data surfaces' half. Spec over mockup.
- **The brand mark is 24px, not 26.** 26 is not on the spacing scale and the
  scale is closed. Same disposition as feature 034's 44 → 48 empty-state well.
- **The guardian dot is the design system's `StatusDot` (13px), not the mockup's
  7px circle.** A second dot at a second size would be a status shape nothing
  else uses; the one in the library already means "healthy" everywhere.
- **The counts differ from the mockup's, because the data does.** The mockup
  draws Incidents 3 and Approvals 2. Against the `populated` scenario the shell
  shows Approvals 2 and Runs 2 — the incidents endpoint is projected and the
  shell does not read it yet, and two runs in that dataset failed. The mechanism
  is the same; the numbers are the fixtures'.
- **The page body is a sentence.** See §3.

`03-screen-dashboard.png` moved from `pending` to `baselined` in the registry and
now names the shell as its surface, with a note saying the frame is reviewed here
and the panels inside it are reviewed again when the data surfaces land.

## 8. NFR-001 is a deadline, not a hope

*"The shell MUST render before any page data resolves"* is easy to write and easy
to lose: the shell's own layout reads four things before it can draw, and three
of them are not the frame.

So the three that are not — the notification list, the recent runs, the guardian
line — are raced against `CONSOLE_SHELL_READ_TIMEOUT_MS` and fall back to empty.
The viewer has no deadline, because there is no honest frame to draw without one
and a refusal is the correct failure.

**What is not asserted in a browser**, and why: a server-side fetch cannot be
stalled from inside Playwright, so "the frame renders while the data does not" is
proved in the unit suite, with the page suspended inside a boundary exactly where
the router puts one. The browser asserts the two things it can see — that first
paint is inside its budget on three routes, and that the whole frame is in the
HTML with **JavaScript disabled**, which is the strongest form of NFR-004 there
is.

## 9. Task-by-task notes

- **T-003 (generate the API client, fail on drift).** Already done by feature
  033 and unchanged. The shell adds no hand-written client.
- **T-005 (not-found inside the shell).** Needs a catch-all —
  `(shell)/[...unmatched]/page.tsx` calling `notFound()` — because Next renders
  the *root* not-found outside every layout, which would drop the navigation at
  the exact moment a lost reader needs it.
- **T-013 (impersonation banner on every route).** Rendered by the shell above
  the router's children rather than by a page, so no page can forget it. The test
  asserts it precedes `main` in document order.
- **T-016 (breadcrumb where the route is nested).** `trailFor` returns one crumb
  for a top-level area and the header renders no breadcrumb for a trail of one —
  a breadcrumb saying only where you already are is furniture. The nested form is
  tested with a synthetic crumb, because no nested route exists until 036.
- **T-017 (scroll restoration on return to a list).** The navigation entries are
  the router's own `Link`, so a transition is a segment fetch and the App Router
  restores scroll on back and forward. **There is no test**, because there is no
  list and no detail page to make a round trip between; the test belongs with the
  first list screen, and 036 is where it goes.
- **T-018 (areas contribute commands).** `src/shell/commands.ts` builds the
  registry from the route manifest, the recent runs and the actions, and drops
  everything the viewer may not run. Areas contribute by being in the manifest,
  which is one fewer list to keep level than a separate registration call.
- **T-020 (an item resolved elsewhere clears without a refresh).** A browser
  event (`ninjasre:attention-resolved`) rather than a callback threaded through
  every screen: the thing that grants an approval is a page three components
  deep and the centre is in the shell. The shell listens; anything may publish.
- **T-024 (absolute timestamp available wherever a relative one is shown).**
  Enforced by construction: `timestamp()` is the only function that returns a
  relative time and it returns the absolute instant and the ISO form with it.
  There is no function that yields a relative time alone.
- **T-026 (budgets asserted in CI).** Two numbers in
  `config/constants/console.py`, read by `tests/e2e/budgets.spec.ts` out of that
  file rather than restated, and run by `make console-e2e` — which CI runs.

## 10. Things added that the tasks do not ask for

- **`fixtures/contract/roles.json`, generated by `tools/console_roles.py`.**
  SC-003 says "for every role in the role order". The console cannot import
  `platform.identity.permissions`, and writing the role table in TypeScript would
  be a second copy of the catalogue in a language the server does not compile.
  Generating it into the fixture tree — which `console/AGENTS.md` already permits
  the console to read — and comparing the committed file against a fresh
  generation gives the matrix the real roles with a drift check behind them.
- **Nine icons.** `GridIcon`, `ListIcon`, `SitemapIcon`, `BrainIcon`,
  `ClipboardIcon`, `BellIcon`, `ContrastIcon`, `MenuIcon` and `CompassIcon` —
  eight of them traced from the shapes the reference navigation draws, on the
  same 24-unit grid at the same 2-unit stroke as the rest of the set. The design
  system's own rule is that a screen needing something absent adds it to the
  library rather than styling locally.
- **Two tokens.** `SHELL.sidebar` (236) and `SHELL.topbar` (52), plus
  `SIDEBAR_BREAKPOINT` (768). Neither measurement is on the spacing scale and
  neither should be; they are tokens so the shell names them instead of writing
  them, and `w-sidebar` / `h-topbar` are the utilities that reach them.
- **`useSyncExternalStore` for the three browser-only values.** The clock, the
  stored theme and the locale cookie. A state read inside an effect renders once
  with the server's answer and once with the browser's, which is a visible
  correction on every load — the same failure the no-flash script exists to
  prevent, arriving through a different door.

## 11. Test-first sequencing

Followed per module, for the reason every feature since 020 gives: a suite
written against modules that do not exist can only fail on `ImportError`, which
proves nothing.

The catalogue test was written and confirmed red against a missing `src/i18n/`.
The guard test was written against the route manifest before the middleware
existed. The single-collapse test was written before the controller and stayed
red until the collapse was a property of there being one controller rather than
of each caller checking. Three of the browser tests stayed red against real
defects rather than against missing modules — see §12.

## 12. Five defects the tests found, and one that reading found

- **The topbar ran 22 pixels off the side of a 320-pixel viewport.** Found by the
  overflow assertion. Fixed by narrowing the bar's own gutter below the
  breakpoint, hiding the theme switch below `sm`, and reducing the primary action
  to its shape with the label still in its accessible name — nothing is lost to
  anybody who cannot see the icon.
- **The drawer opened at the bottom of the page.** `Drawer` is a panel, not a
  position: rendered inline it appended below the main content, so at 320 pixels
  "open the navigation" scrolled somewhere rather than showing anything. Fixed by
  positioning it in the shell, which is where a decision about *where* a panel
  goes belongs.
- **An unmatched address lost the whole shell.** Next renders the root not-found
  outside every layout. Found by the browser test asserting the sidebar is still
  there; fixed with the catch-all in §9.
- **The palette carried the last search into the next opening.** The reset lived
  in an effect keyed on `open`, and the ordering meant a reopened palette showed
  the previous query with the first match highlighted — one `Enter` from running
  the wrong command. Fixed by not rendering it at all while closed, so every
  opening is a fresh mount.

**Signing out did not sign anybody out.** Found by reading rather than by a
test, which is why it is worth saying: the account menu ended the *client's*
session and navigated to the sign-in, and left the HTTP-only cookie exactly where
it was. The guard reads that cookie, so the next person at that keyboard typed
the address and was inside — while the operator who pressed the button believed
they were not. The control now ends the session on the server first
(`src/session/end.ts`), and a browser test signs out, reads the cookie jar, and
then tries a second route.

A further one was in a test rather than in the console: the first render of the
suspended-page assertion threw a new promise on every render, which suspends for
ever rather than once. The promise is now created outside the component, which is
what a real suspending read does.

**A sixth was a flake this feature caused and had to fix.**
`tests/unit/gallery-page.test.tsx` rendered the whole gallery five times — once
per assertion — and queried it with one accessible-name lookup per primitive.
That was already the slowest file in the suite; the nine icons this feature adds
to the set pushed its first test past the runner's five-second timeout on a
loaded machine, and it failed once inside `make verify` while passing every time
in isolation. Fixed at the root rather than by raising the timeout: the page is
mounted once for the file, and the thirty accessible-name queries became one pass
over the headings. Worst test in that file: 1054ms → 133ms.

**And a seventh, found while reading rather than by a test.** `TrailCrumb`
carried a `string` label and a `translate` flag, so rendering it needed an
assertion (`crumb.label as 'nav.label'`) to hand a string to a function that
takes a catalogue key. It is a discriminated union now: a crumb that says it is
translatable is *typed* as a key, and there is no assertion left for a key that
is not a key to get through.

## 13. Gate

`make verify` green: **9,784 passed, 20 skipped** in 4m45s — lint, format, mypy,
the seven import contracts, every guard check, and the console half in full: the
lockfile, format, lint (the design-literal rule, the new untranslated-string rule
and the stylesheet scan), types, **601 unit tests** at 94.7% statements / 90.1%
branches against a floor of 90, the API client drift check, the standalone
production build, both bundle budgets, **45 browser tests** against the committed
dataset, and **eleven visual comparisons** inside the pinned image.

Of the Python total, 31 are this feature's own contract tests in
`tests/contract/console/test_console_shell.py` — including a map from each
success criterion to the named test that proves it, so a proof that is deleted or
renamed fails there. The console's 601 unit tests and 45 browser tests are run by
the console gate rather than by pytest. The working
tree is clean afterwards.
