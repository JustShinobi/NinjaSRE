# The console

The web console: a TypeScript application, served by a process of its own, that
talks to the deployment over the REST API and to nothing else.

Read the root [`AGENTS.md`](../AGENTS.md) first. What follows is what is
different here.

## It is not a Python package, and that is load-bearing

`console/` is a peer of the seven Python tiers rather than a member of one. It
has no `__init__.py`, no module in it is importable, and the tier table's
`console` row says so:

| Tier | Packages | May import | Must never import |
|---|---|---|---|
| — | `console` | the REST API, over HTTP | every Python package |

`make check-console-boundary` enforces both directions: no Python module imports
`console`, and no console file reaches into `capabilities/`, `config/`, `core/`,
`gateway/`, `integrations/`, `platform/`, `surfaces/`, `tests/` or `tools/`. It
is a guard script rather than an `import-linter` contract because `import-linter`
reasons about importable Python packages — giving this directory an `__init__.py`
so a contract could name it would create the very thing the row forbids.

The one exception is `fixtures/`, which the console may read. It is data, it is
generated from the application by checks that already exist, and reading it is
how the console stays a client rather than becoming a second implementation.

## The toolchain is pinned, and provisioned by the gate

Nothing here assumes Node is installed.

| Concern | Where it is pinned |
|---|---|
| Node | `.node-version`, with a SHA-256 per platform in `toolchain.lock.json` |
| pnpm | `packageManager` in `package.json`, and `toolchain.lock.json` |
| Browser | `@playwright/test` in `package.json` |
| Capture image | `toolchain.lock.json`, by digest |

`make console-setup` provisions all of it. It looks for a Node already on `PATH`
at exactly the pinned version, and otherwise downloads the official archive and
refuses it unless it hashes to the committed digest. Set `NINJASRE_NODE_MIRROR`
to fetch from somewhere else; the digest it has to match is the same one, so a
mirror is a different address rather than a lower standard.

The archive is unpacked into `.toolchain/`, which is ignored by git and safe to
delete — the next run provisions it again.

## Every check, and how to run one

`make verify` runs the static checks through `make console-static`. The complete
set remains available through `make console-check`, and each check is also a
target of its own, because a contributor fixing a type error should not have to
sit through a browser suite to find out whether they fixed it.

| Target | What fails it |
|---|---|
| `make console-lockfile` | `pnpm-lock.yaml` no longer describes `package.json` |
| `make console-format-check` | a file the formatter would rewrite |
| `make console-lint` | a lint rule, including the type-aware ones |
| `make console-typecheck` | a type error anywhere in the tree, tests included |
| `make console-test` | a failing unit test, or coverage below the declared floor |
| `make console-client-check` | the committed API client is not what the document generates |
| `make console-build` | the production build |
| `make console-budget` | the compiled stylesheet or the icon set is over its declared budget |
| `make console-e2e` | a browser test against the built console, including the route-transition and first-paint budgets |
| `make console-visual` | a screen that differs from its committed baseline |

On a machine with no toolchain and no container runtime, the checks that need
them report a named skip and succeed — the same way the chaos and cloud suites
already do, because a gate that goes red for a reason the contributor cannot act
on is a gate they learn to bypass. CI sets `NINJASRE_CONSOLE_TOOLCHAIN=required`,
and then a skip is a failure. Three things are never skipped, whatever the
machine: a drifted lockfile, a stale committed client, and a check that ran and
failed.

## The application shell

`src/shell/` is the frame every screen sits in, and `src/app/` is the route tree
inside it. Four things about it are load-bearing.

**`src/shell/routes.ts` is the only list of what routes exist.** The sign-in
guard walks it, the role matrix walks it, the deep-link test walks it, and the
palette's navigation commands are built from it — so a route added tomorrow is
covered by tests that already exist rather than by tests somebody remembers to
write. Each entry carries the permission the *gateway* requires on the data that
area reads, copied by name; `tests/contract/console/test_console_shell.py` holds
each one against the gateway's own route table.

**Authentication is checked above the router.** `middleware.ts` runs before
routing, over every path but the build output, and there is deliberately no
per-page check anywhere. The decision itself is `src/session/guard.ts`, a pure
function, so the suite can enumerate the manifest against it.

**A 401 is a session event.** Every refusal reaches one `SessionController`,
which ends the session once and remembers the route to come back to. Three
concurrent 401s produce one prompt because there is one controller, not because
each caller checked whether another had already acted.

**Permissions decide presence.** A control the viewer cannot use is not in the
DOM. `tests/unit/shell/role-matrix.test.tsx` asserts that for every role ×
every area, walking the role catalogue the platform generates into
`fixtures/contract/roles.json` — the console never decides what a role holds.

The credential never enters browser-readable storage. `src/app/api/session/`
offers it to the API origin, and keeps it in an HTTP-only, `SameSite=Strict`
cookie; a second, readable cookie carries only the instant the session ends,
because the expiry warning has to be rendered before the expiry.

## The data surfaces

`src/surfaces/` is what fills the frame, and `src/surfaces/screens/` is one
module per area. Five things about it are load-bearing.

**A region that fetches is a `Panel`, and a `Panel` cannot be written without an
empty state.** `PanelProps.empty` is required and `EmptyState` throws on a blank
body or a blank action, so "say what would be here and how to get it" is a thing
the type system asks for rather than a thing a reviewer notices. Each panel also
has its own error boundary and its own retry, which is what "panels fail alone"
means in practice: a dashboard is six independent questions, and one
unanswerable question must not blank the other five.

**Whatever a screen is showing is in its address.** `src/surfaces/url-state.ts`
is pure functions over a query string, read by the *server* component that
renders the screen. A column header is an anchor carrying the sorted view's
address and a filter is a navigation, so there is no code path that changes what
a list shows without changing the address — which makes "a view can be sent to a
colleague" true by construction, and makes sorting work with JavaScript
disabled.

**There is one transcript.** `src/surfaces/transcript.ts` turns either shape a
run arrives in — a replay or a stream — into one sequence of events, and
`transcript-view.tsx` is the only component that draws one. Both halves are
asserted structurally, in the unit suite and again in
`tests/contract/console/test_console_surfaces.py`, because a live view and a
history view are the two files this console is most likely to grow by accident
and the divergence is always in the direction of the recorded one showing less.

**Nothing here computes what the server computes.** No configuration merge, no
permission derivation, no masking decision, no blast radius. The configuration
preview is a `POST` forwarded by `src/app/api/preview/` and the response is
rendered verbatim; a contract test asserts that no merge exists anywhere in
`src/`. The two route handlers under `src/app/api/` exist only because the
credential is in an HTTP-only cookie and a browser cannot present it.

**A long list is windowed and a transcript is paged**, and they differ because a
row is a fixed height by contract and a transcript entry is not. Both say how
many there are; neither truncates silently.

`src/lib/api.ts` carries one more thing worth knowing: `PROJECTED_PATHS`, the
closed list of endpoints a deployment will serve and the API document does not
declare yet. It returns `unknown`, a 404 from one of them is *empty* rather than
*error*, and the contract test requires the list to **shrink** — an endpoint that
lands in the document has to move to the generated client.

## The live layer

`src/live/` is what makes a screen feel connected: a transcript that grows, a
card that closes when a colleague decides it somewhere else, a run an operator
can take control of. Five things about it are load-bearing.

**The reducer is pure and lives outside React.** `src/live/reducer.ts` is a
`(state, event) => state` with no DOM, no timer and no network in it, because
the property this whole layer exists for — every event exactly once, in order,
across a reconnection — is the one most likely to regress and has to be provable
in a unit test against a source that raises, replays and reorders. Three rules
do the work: a sequence at or below the cursor is discarded, a sequence beyond
the next one is *held* rather than rendered, and the cursor is the last event
actually applied rather than the last one received.

**One subscription per run, shared.** `src/live/store.ts` holds the connection,
reference-counted; the last screen watching a run closes it. A page whose
transcript, cost panel and approval card each opened their own stream would
triple the deployment's fan-out and let the three disagree about what has
arrived — the count saying two above a card that has already closed.

**A disconnected stream never presents itself as live.** The connection state is
always on the transcript's header, including when it is fine, and the
reconnection is bounded: after the same number of attempts the deployment's own
reader allows, the console says it has stopped and offers a manual reconnection.
A stale transcript and a stalled investigation look identical, and an operator
who cannot tell them apart goes and does the run's work by hand.

**The stream is read with `fetch`, not `EventSource`.** An `EventSource` cannot
present a cursor on the *first* connection — only on its own reconnections — and
reports every failure as one opaque error, so a session that expired mid-stream
would be retried as if it were a dropped packet. `src/live/sse.ts` parses the
framing as a pure function and `src/app/api/stream/[runId]/` is the courier that
adds the credential: it turns the `cursor` query into `Last-Event-ID` and pipes
the body through byte for byte.

**Every optimistic write keeps a snapshot, and a toast is never the only
record.** `src/live/optimism.ts` records what a write replaced so a refusal can
put it back *with the deployment's reason*; `src/live/outcomes.ts` will not let
an outcome exist without naming somewhere durable it is also written down, and
the type is what enforces that rather than a reviewer.

`tests/contract/console/test_console_live.py` holds the vocabulary against the
Python that defines it: the cursor separator, the reconnection bound, which
event kind closes a card, and which kinds end a run.

## Every user-visible string comes from the catalogue

`src/i18n/en.ts` is the source; `MessageKey` is derived from it, so a component
naming a key that does not exist fails to compile. `src/i18n/pt-BR.ts` is typed
as *partial* on purpose: a total type would make the completeness test unfailable,
and a test that cannot fail proves nothing. The fallback is per key rather than
per locale — a locale missing one string keeps every other string it has.

`eslint-rules/no-untranslated-strings.mjs` runs over the surfaces a viewer
reaches and rejects literal text in a component and literal sentences in the
attributes a person hears. The completeness test can only compare the locales it
is given; it has nothing to say about a string that never reached a catalogue,
which is exactly the string that ships untranslated.

## The design system

`src/design/` is the vocabulary and `src/components/` is what it composes into.
Everything on a screen comes from there; a screen that needs something absent
adds it to the library rather than styling locally.

**Tokens are data.** `src/design/tokens.ts` is the single input to three
readers: `css.ts` renders it into the custom properties the document carries,
the `@theme` block in `src/app/globals.css` maps it onto Tailwind utilities, and
`contrast.ts` measures it. The token names are compared against the Tailwind
theme in both directions by `tests/unit/design/css.test.ts` — a utility pointing
at a token nobody declares fails, and a token no utility exposes fails too,
because a token a component cannot reach is one somebody works around with a
literal.

**Colour is declared by role.** `surface`, `sunken`, `raised`, `text`, `muted`,
`accent`, `border`, `border-strong`, and five semantic roles each with a
foreground and a tint. Both themes declare the same names at different values,
so a screen written against tokens works in both by construction. Every pair is
measured on every run: body text at 4.5:1, control boundaries at 3:1. `border`
is decorative and deliberately exempt — collapsing it into `border-strong` would
either make every table line heavy or every control boundary non-compliant.

**Status never rides on colour alone.** A status maps to a role and a shape
through `src/design/status.ts`, and nothing else decides. A status the console
has never heard of is neutral with its own raw text — never blank, never an
error.

**The scales are closed sets**, and they are enforced twice.

The first enforcement is the stylesheet, and it takes two declarations rather
than one. `@theme inline` in `src/app/globals.css` names the seven spacing
steps, but `@theme` *adds* names and never clears what Tailwind's own theme
declared — so `--spacing: initial` is what actually closes the scale, and
`--container-*: initial` closes the second set of lengths that arrives with it.
With no base there is nothing to multiply, so `p-9`, `max-h-96` and `max-w-md`
are not utilities and produce no CSS at all. `--spacing-0` is declared
alongside, because zero is the removal of a step rather than an eighth one and
`inset-0` has to keep working. `tests/unit/design/spacing-scale.test.ts`
compiles the real stylesheet and asserts both halves; the claim was false for a
year without it, which is why it exists.

Measurements that are genuinely not steps get named tokens and their own
utilities, the way `SHELL` and `COLUMN_WIDTHS` already did:
`max-h-scroll-pane`, `max-h-scroll-entry`, `h-scroll-slot`, `max-w-reading`
and `w-stroke-emphasis`. A scroll ceiling is measured from how much content is
worth showing at once, and the largest spacing step is a gutter — rounding one
to the other would be a worse answer than naming it.

The second enforcement is `eslint-rules/no-design-literals.mjs`, which rejects a
colour, an off-scale length, a raw duration and every arbitrary-value utility in
`src/`, with `scripts/check-css-literals.mjs` covering the stylesheets ESLint
does not parse. Its list of spacing-taking utilities covers the width, height,
inset and translate families as well as padding, margin and gap — it did not,
which is how four off-scale lengths passed both checks at once. It is a list
rather than an inference, because `z-10` and `grid-cols-3` also end in a number.
Two files are exempt, and both are where values are *declared*:
`src/design/tokens.ts` and `src/design/css.ts`.

The two checks catch different failures and neither replaces the other. The
closed scale is stronger and arrives earlier, but it fails *silently* — an
element with no rule keeps whatever it inherited, and the screen looks nearly
right. Lint is what turns that silence into an error naming the file.

**Reduced motion removes the animation.** One rule in the base layer sets every
duration to `--dur-none`, which is a member of the duration scale rather than an
absence. A component that wrote its own inline duration would escape it, which
is why durations are the `motion-*` utilities and never a number.

## The gallery is the contract

`/gallery` renders every primitive in every declared variant and state. It is
what the visual suite screenshots and what the accessibility audit walks, and
`tests/unit/gallery.test.tsx` compares it against the barrel in
`src/components/index.ts` — a primitive that is exported and not registered
fails by name. Nothing in the console links to it, and a test asserts that.

The audit is in `tests/unit/support/accessibility.ts` rather than in a
dependency, for the reason every other dependency is refused here. Its declared
level is: no violation of any rule it implements, anywhere in the gallery. Rules
needing layout or a real screen reader sit outside it and are covered elsewhere
— contrast by the token test, overflow and theme parity by the browser suite.

## The API client is generated, never written

`src/api/schema.ts` is generated from `fixtures/contract/openapi.json` — the
committed copy of the gateway's own document — by `make console-client`. It is
committed, and `make console-client-check` fails when it differs from a fresh
generation.

Two consequences worth stating. The generation needs no network and no running
gateway, so an air-gapped build works. And the console cannot hold a second
opinion about what the API returns: a route that changed shape reaches it as a
failing type check rather than as a client that compiles and 404s.

`src/lib/api.ts` is the only module that makes a request. Everything else goes
through it — which is also why it is the one place a 401 is published to the
session controller.

`fixtures/contract/roles.json` is generated the same way, by
`python -m tools.console_roles write`, and compared against a fresh generation
by the Python suite. It exists so the role matrix can walk the roles the
platform actually declares instead of a list written in TypeScript.

## Nothing may leave the deployment

No font host, no icon CDN, no analytics, no error reporter. Every asset is
bundled and served by the deployment.

Two things hold this. A lint rule rejects a literal external origin in console
source. And `tests/e2e/network.spec.ts` watches every request a production build
issues and fails on any host the operator does not run — which is the half that
catches a bundled stylesheet that turns out to point at a font host.

## Visual baselines, and what accepting one means

Baselines live in `visual/baselines/` and are compared against captures from one
container image, pinned by digest. Font rasterisation differs between operating
systems and between font packages on the same one, so a baseline captured
anywhere else produces differences that mean nothing — and a visual gate
reporting differences that mean nothing is one people stop reading.

`make console-visual` compares. `make console-visual-accept` recaptures, which
rewrites committed PNGs: **the acceptance is the commit somebody reviews**, not
a flag on a command.

`visual/screens.json` is the registry, and it is what makes design fidelity
checkable rather than merely intended:

- a design reference in `visual/mockups/` that appears in neither list fails the
  suite by name, so a design cannot arrive and be forgotten;
- a reference marked `pending` must name the surface that will implement it;
- a screen marked `baselined` must have a committed baseline **and** an
  acceptance record naming the reference it was first reviewed against — or, if
  there is no reference, a sentence saying why. After that first acceptance,
  ordinary visual regression keeps the screen matched.

## The browser suites

`tests/e2e/` drives a browser against the built console and a real gateway.
`tools/console_e2e.py` starts both and takes them down; the suite is handed an
address and owns no process, because a browser test that also owns process
lifecycle is a browser test that hangs.

The visual suite has a third: `scripts/fixture-server.mjs`, a Node server that
answers every read a surface makes from the same committed JSON. The capture
image has a Node and no Python, and the shell resolves the viewer on the server —
so without something answering, every capture would be of the sign-in page. The
unit suite imports the same module, so a screen tested in `jsdom` and a screen
photographed in a browser are looking at one dataset. Its endpoint table is held
against the mock plane's own catalogue by the Python suite; it is not a second
mock data plane, because it does not validate, does not write, and answers reads
alone.

Two backings for the behaviour suite. `mock` is the committed dataset served by `tools.mockplane` — every
timestamp in it is shifted to one fixed instant, which is what makes
`make console-e2e-sweep` (twenty consecutive runs, any flake is a defect) worth
running. `compose` is the deployment's own compose definition: a real gateway
against a real database, run by its own CI job.

There are no retries. A retry hides a flake, and a hidden flake is why suites get
disabled. Anything that cannot be made deterministic becomes a unit test instead
— never a disabled test.

## Seeded failures

`fixtures/` holds files that are broken on purpose: a type error, a lint
violation, a format violation, a failing unit test, a failing browser test.
`tests/contract/console/test_console_gate.py` splices each one into the tree,
runs the check it belongs to, and requires it to fail and to name the file.

A check nobody has watched fail is a check that might be walking an empty file
list, and the repository would look exactly as clean either way. That is the
whole reason the directory exists, and it is why the lint, format and type
configurations all exclude it.
