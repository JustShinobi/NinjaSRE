# Deviations — 034 Console Design System

Every place the implementation differs from `spec.md`, `plan.md`, `tasks.md` or
`design.md`, and why. Recorded as they happened rather than reconstructed
afterwards. Not committed — this whole directory is gitignored.

---

## 1. Four colour tokens the design document does not tabulate

**Documented.** `design.md` §2 lists thirteen light tokens and thirteen dark
ones, plus five tinted backgrounds per theme. Every one of those is implemented
**byte for byte**, and `tests/unit/design/tokens.test.ts` compares each against
the published value rather than against a measurement.

**Added.** `spec.md` FR-001 asks for five semantic roles "each with a foreground
pair". The document gives `--on-accent` and `--on-danger` and stops. So four
more were derived:

| Token | Light | Dark | Why this value |
|---|---|---|---|
| `--on-success` | `#ffffff` | `#0d1117` | The same choice the document makes for `--on-danger` in light: white on the role. Measured at 6.44:1 and 10.68:1. |
| `--on-warning` | `#ffffff` | `#0d1117` | 5.93:1 and 10.04:1. |
| `--on-info` | `#ffffff` | `#0d1117` | 6.60:1 and 8.83:1. |
| `--neutral`, `--on-neutral`, `--neutral-bg` | `#59626d`, `#ffffff`, `#f5f7f8` | `#9aa5b1`, `#0d1117`, `#0a0e13` | The mockup's own `.b-mute` chip is `--muted` on `--sunken` with a `--border-strong` edge. The neutral role is that, named. |

Every one of them is measured on every run by the contrast test, so none of them
is a value chosen by eye. The dark foregrounds are `--surface` rather than a
darkened tint of the hue: the document's own dark `--on-accent` (`#06231c`) and
`--on-danger` (`#2b0b0c`) are hue-tinted, and inventing three more tints would
have been three colours nobody drew.

**One value taken from the mockup rather than the document.** `design.md`'s
light table has no `--raised` row, but the contrast table lists `text / raised`
at 18.18 for light — the same as `text / surface` — and `mockups.html` declares
`--raised:#ffffff`. Light `raised` is therefore `#ffffff`, which is what both
sources say.

## 2. The Tailwind theme is not generated, and could not be

**Planned.** T-005: *"Generate the Tailwind theme from the token table; assert
the generated theme and the table cannot diverge."*

**Done.** The theme is written by hand in `src/app/globals.css` and held to the
table by a test that compares the two sets of names **in both directions**.

**Why.** Tailwind 4 reads its theme from CSS at build time, before any
TypeScript in this project has run. Generating it would have meant a code
generation step, a committed generated file, and a drift check — the shape the
API client already has, and one more file an operator has to audit. The property
the task actually asks for is that the two cannot diverge, and that is what is
enforced: a `@theme` entry pointing at a token nobody declares fails, and a token
no utility exposes fails too, *because a token a component cannot reach is a
token somebody works around with a literal*. A third test asserts the `@theme`
block contains no colour at all, so it can only ever reference.

**What is better than generation.** The spacing scale is given to Tailwind as
seven explicit keys with no base value, so `p-9` is not a utility and produces no
CSS whatsoever. An off-scale value fails at the point of use rather than at the
point of lint, which is earlier and cannot be suppressed.

## 3. Two scales the design document implies rather than tabulates

**Border widths.** FR-003 asks for a border-width scale; `design.md` never lists
one. Three steps, each taken from something the mockup actually draws: `1` (every
separator and control boundary), `1.5` (the hollow status ring — the mockup's
`border:1.5px solid var(--muted)`, which needs to read as a ring rather than a
smudge at eight pixels across), and `2` (the focus ring, which the mockup draws
as `outline:2px solid var(--accent)`).

**Density metrics.** FR-014 asks for a comfortable and a compact density
affecting "spacing and control height only". No numbers are published. The
implementation declares exactly three: gap (16 → 12), control height (34 → 28)
and row padding (12 → 8), and a test asserts the metric record has those three
keys and no fourth — because a density that could carry a fourth value could
carry a colour, and then it would be a second theme wearing a different name.

## 4. Token names are role names, not the mockup's shorthand

`mockups.html` uses `--s1…--s7`, `--r1…--r4`, `--f0…--f7`, `--sh1`, `--sh2`. The
implementation declares `--space-1…7`, `--corner-1…4`, `--size-body`,
`--line-body`, `--weight-body`, `--track-body`, `--elev-1`, `--stroke-1`,
`--dur-hover`, `--icon-nav`.

The values are identical. The names are longer because they are read by three
consumers rather than by one 600-line file, and because `--sh1` and `--shadow-*`
would have collided with Tailwind's own namespace while `--radius-N` would have
collided with itself. Two of the eight type steps carry four properties each, and
`--f6` cannot say which of them it is.

## 5. `ConfirmDestructive` is a primitive, and is not on FR-007's list

FR-013 says a destructive action "MUST require an explicit confirmation step that
names the target". FR-007's list of primitives has `Modal` and stops there.

Implemented as a primitive anyway, in `src/components/overlay.tsx`. The reason is
the same one the whole feature rests on: a rule that every screen has to remember
is a rule one screen forgets, and the screen that forgets it is the one deleting a
recovery point. The component takes `target`, `action` and `consequence` as
required props, so a confirmation that does not name what it is about cannot be
written. The safe option sits beside the destructive one, and escape cancels
rather than confirming — each asserted.

## 6. §6 of the design document describes compositions, not primitives

`design.md` §6 gives the anatomy of six things: the stat tile, the attention row,
the proposal card, the transcript event, the meter and the empty state. Three of
them are primitives and are implemented as such:

| Anatomy | Where |
|---|---|
| Stat tile | `StatTile` — label with icon, one figure at `display`, mandatory context line. It **throws** without the context line rather than rendering a figure nobody can act on. |
| Meter | `ProgressBar` — 6px, bordered so it is visible at 0%, accent under the first threshold, warning between, danger above, number always beside it. |
| Empty state | `EmptyState` — icon, heading, body, action, all four required, and it throws without the body or with a blank action label. |

The other three — the attention row, the proposal card and the transcript event —
are **compositions of these primitives with product data**, and the product data
is feature 036. The parts they are made of exist here (`Badge`, `Card`,
`DataList`, `Timeline`, `CodeBlock`, `DiffView`, `ConfirmDestructive`,
`ErrorState`), and `Timeline` already carries the transcript event's header line
including the side-effect marker. Building them here would have meant building
three screens' worth of composition against no data, which is precisely the risk
`plan.md` names first.

## 7. The accessibility audit is written here rather than depended upon

**Planned.** T-025: *"Accessibility audit over every gallery entry; no
violations at the declared level."* Nothing says which auditor.

**Done.** `console/tests/unit/support/accessibility.ts`, about two hundred lines,
run over every gallery entry individually and over the composed gallery page.

**Why.** The reason Article X gives about every other dependency, and one more:
this suite runs inside `make verify` on machines with no network, and an audit
package is a package an operator has to audit. **The declared level is stated in
the module**: no violation of any of the eight rules it implements, which are the
ones decidable from a rendered tree — an unnamed interactive element, an
unlabelled form field, an image with no alternative text, a duplicated
identifier, an ARIA reference pointing at nothing, a positive tabindex, a
focusable element inside an `aria-hidden` region, and a role the console does not
declare. What is outside the level is said too: contrast is proven by the token
test, focus visibility by the single ring in the base layer, reading order by the
component tests that press Tab, and overflow and theme parity by the browser
suite.

**The audit has been shown failures.** Six tests hand it a tree that breaks each
rule and require it to say so, because an auditor nobody has watched fail is
indistinguishable from one walking an empty list.

## 8. The icon set is drawn here

FR-005 asks for "a single icon set". Twenty-four outline icons are drawn in
`src/design/icons.tsx` on a 24-unit grid with a 2-unit stroke, at the four sizes
`design.md` §5 names (13 inline, 15 nav, 19 page header, 20 empty state).

Each icon is a **named export** rather than an entry in a lookup table, which is
what makes the set tree-shakeable: a table would put all twenty-four in every
bundle and NFR-004 would be satisfied only on paper. First paint cannot be
blocked on the set because there is nothing to load — no font, no sprite, no
request — and a test asserts every icon renders no `<image>`, no `url(` and no
`xlink:href`.

## 9. What the lint rule polices, and the two files it does not

`design/no-design-literals` runs over `src/**` only.

- **Tests are exempt**, because `tokens.test.ts` states the published colour
  values and compares them against the table. That is the opposite of hard-coding
  one, and a rule forbidding it would forbid the assertion that keeps the table
  honest.
- **`src/design/tokens.ts` and `src/design/css.ts` are exempt**, and that is the
  whole exemption: the first is where values are declared and the second turns
  them into custom properties. A Python contract test
  (`test_the_token_table_is_the_only_place_a_colour_is_written`) independently
  sweeps every other file in `src/` for a hex colour, so the exemption cannot
  quietly widen.
- **Stylesheets are covered by a second command.** ESLint parses JavaScript;
  `scripts/check-css-literals.mjs` runs the same detection over every `.css` file
  under `src/`, exempting only lines that declare a custom property. Both run
  under `make console-lint`, and a test asserts the lint script still calls the
  second one.

**One deliberate narrowing, after a false positive.** The rule first flagged
lengths and durations in *any* string, which rejected the copy "last swept 41s
ago" and "3m 48s". A rule that fires on prose is a rule somebody switches off, so
measurements are now flagged only in a style context — a bare value, a CSS
declaration, or a string inside a `style` attribute — while colours, arbitrary
utilities and off-scale utility steps are still flagged everywhere. The seeded
fixture proves all four kinds still fail.

## 10. The gallery is one route, and six baselines

**Planned.** T-023 a gallery route; T-026 baselines at 320, 768 and 1440 in both
themes; T-027 a theme-parity test.

**Done.** `/gallery` renders every primitive × every variant × every state, and
`visual/screens.json` registers six captures of it — three widths × two themes.
The registry gained `viewport` and `theme` fields, which is what turns one route
into six screens; the existing coverage tests were not touched and still hold.

**The acceptance records.** Feature 033's mechanism requires a baselined screen to
name the design reference its first acceptance was reviewed against. Four of the
six name one, and the assignment is stated rather than implied:

| Capture | Reviewed against | What was compared |
|---|---|---|
| `gallery-1440-light` | `01-tokens-colour.png` | Every role pair with its measured ratio, and the seven status shapes |
| `gallery-768-light` | `02-tokens-scales.png` | The type, spacing, radius, border and duration scales as closed sets |
| `gallery-320-light` | `07-states-empty-error.png` | The empty and error states, at the narrowest declared width |
| `gallery-1440-dark` | `08-theme-dark.png` | The same geometry under the dark token set |

The other two (`gallery-768-dark`, `gallery-320-dark`) record in prose that there
is no reference for the combination — the design draws one picture of each theme
and each width, not six — so they exist to catch a regression rather than to
record a review. That is the sentence a reviewer can argue with, which is what
the mechanism asks for in place of a missing field.

**`08-theme-dark.png` was reassigned.** Feature 033's registry gave it to "the
console application shell". `design.md` for *this* feature lists it as one of its
three images, and what it documents is the token set rather than a shell. It is
now owned here, and its note says so.

**T-027 is stronger than a pixel diff.** "A pixel diff between themes differs in
colour only" is asserted in the browser as *every bounding box on the page, to
the pixel, identical between the two themes* — which is the property a pixel diff
was standing in for, and which a pixel diff of two differently-coloured pages
cannot actually express.

**SC-005 is a browser assertion, not a screenshot.** "No horizontal overflow" is
`scrollWidth - clientWidth <= 0` at each width and at 200% zoom, and the failure
names the elements that ran past the viewport. A screenshot can only show it to
somebody who looks.

## 11. Fidelity: where the built system differs from the mockups

Recorded per the definition of done. Nothing below is a difference in a *value*;
every colour, size, radius and duration equals its documented number.

- **The gallery is not a screen in the mockups.** `01`, `02` and `07` are drawn
  as fragments inside a document; the gallery renders the same content as a
  route, with a page header and named sections. The comparison is of content and
  anatomy, not of page furniture.
- **The colour section shows more pairs than the reference.** The mockup draws
  eight swatches; the gallery draws every pair the contrast test measures — 47 in
  each theme — with the ratio computed at render time rather than written under
  the swatch. A number written under a swatch stops being true the day after it
  is written.
- **The scale section adds the border, duration and icon scales.** The reference
  shows type, spacing and radius. FR-003 declares six scales, so all six are
  shown.
- **The status chips are the badge primitive.** The mockup hand-draws six chips;
  the gallery renders `Badge` for all thirteen declared statuses plus one nobody
  declared, so the "unknown status is neutral with its raw text" rule is visible
  rather than asserted elsewhere.
- **`--sh1`/`--sh2` shadow values are the mockup's**, including the dark theme's
  heavier pair. The design document names two elevations without giving values;
  the mockup gives them and they are used verbatim.
- **The empty state's icon well is `48px` (spacing step 7), not the mockup's
  44px.** 44 is not on the spacing scale and the scale is closed. This is the one
  place a documented pixel value was moved onto the nearest step rather than
  reopening the set, and it is a four-pixel difference in a decorative container.

**Fidelity was judged against fixed data**, as the definition of done requires:
the `runs` baseline is captured against feature 032's `populated` scenario
through the committed fixture set, and the gallery renders fixed specimen data
declared in the registry, so a difference is a difference in the console.

## 12. Five defects the tests found, all fixed rather than worked around

Recorded because they are the argument for writing the checks before believing
the components.

- **The tooltip pointed `aria-describedby` at an element that was not there.**
  The reference was rendered whether or not the tooltip was open, so for the
  entire time the tooltip was closed the control carried a description a screen
  reader silently drops. Found by the audit's dangling-reference rule; fixed by
  attaching the reference only while the tooltip is in the tree.
- **Every unselected tab named a panel that did not exist**, for the same reason:
  only the selected panel is rendered. Fixed by putting `aria-controls` on the
  selected tab only, which is what the pattern permits precisely so that panels
  can be rendered one at a time.
- **The audit itself was wrong about icon-only controls.** It computed the
  accessible name from `textContent`, which includes the contents of `aria-hidden`
  subtrees — so a button holding nothing but a hidden glyph looked named. That is
  the exact case the rule exists to catch. Fixed with a reader that skips hidden
  subtrees, and the fix is what made the seeded failure test go red first.
- **The date range took the page sideways at 320 pixels.** A date input carries
  an intrinsic minimum width larger than a narrow column, and a flex item that
  will not shrink below its content takes everything with it. Found by the
  overflow assertion, which names the offending elements; fixed with `min-w-0`
  and a stacked layout below the breakpoint.
- **The stat tile changed its corner radius while loading.** A geometry change,
  caught by the no-layout-shift assertion in the surface tests, which compares
  the geometry classes across every state. Fixed by putting the radius on both.

A sixth was found in the harness rather than in the console: the theme-parity
assertion failed on a spinner, because a rotating element's bounding box depends
on which frame was measured. The comparison now runs under reduced motion, since
the claim is about layout and not about animation.

## 13. Task-by-task notes

- **T-002 (assert the arithmetic against the Python implementation).** Ten pairs,
  compared to four decimal places against values produced by
  `surfaces/console/theme.contrast_ratio`. Two implementations of WCAG 2.1 that
  disagree in the fourth place eventually disagree about whether a pair passes.
- **T-006 (no flash on load).** The system default needs no JavaScript at all —
  it is a media query in the token stylesheet, guarded with
  `:root:not([data-theme="light"])` so an explicit light choice survives a dark
  operating system. Only the *override* needs code, and the test runs that code
  the way a browser does: as a `<script>` element inserted into the document,
  with `runScripts: 'dangerously'` enabled in the unit runner for exactly this.
  The script writes nothing when there is no stored choice, so a system that
  changes theme while the page is open is still followed.
- **T-013 (form controls).** `Switch` is a real `role="switch"` rather than a
  styled checkbox, because the two are announced differently and "autonomy is
  selected" is not a sentence anybody wants at three in the morning.
- **T-015 (responsive collapse).** Every table cell carries `data-label` with its
  own column header, so the stacked form below the breakpoint prints the header
  in front of the value. Put on the cell rather than asked of each screen, which
  is the difference between a rule and a habit.
- **T-019 (bounded payloads).** `CodeBlock` and `DiffView` both bound at 200
  lines and **say what they bounded and by how much**. A truncation is silent; a
  bound is a fact.
- **T-020 (EmptyState requires a message and an action).** Enforced by throwing.
  The type already makes a missing action impossible, so the runtime guard covers
  what a well-typed caller can still do — an action whose label came from an
  empty string upstream, which renders as a blank button and is the same dead
  end. The original guard also checked for `undefined`; the type checker proved
  that branch unreachable, and dead code that looks like a safeguard is worse
  than no safeguard.
- **T-023 (excluded from production navigation).** There is no navigation yet —
  that is feature 035 — so "excluded" is implemented as: nothing links to it, the
  page says at the top that it is not part of the console, and two tests hold
  both (a Python sweep of `src/` for a `/gallery` reference outside the gallery
  itself, and a browser assertion that the console's own page links to it
  nowhere). When 035 adds navigation, the sweep already forbids adding it there.
- **T-028 (bundle budgets asserted in CI).** A new gate check, `budget`, run by
  `make console-check` straight after the build, with `make console-budget` as
  its own target. Two numbers, both in `config/constants/console.py`: 40 KiB for
  the compiled stylesheet (currently 17 KiB) and 16 KiB for the icon set
  (currently 7 KiB). The icon budget is measured against the source module rather
  than a bundle chunk, because the bundler inlines the icons into whichever chunk
  imports them and there is no one file to weigh — and because the property worth
  holding is that the *whole set* stays small enough that carrying all of it
  would be acceptable.

## 14. Smaller things, recorded because they look like they might be deviations

- **`src/lib/status.ts` moved to `src/design/status.ts`.** Feature 033 shipped the
  status-to-role mapping as a placeholder and said so in its own docstring: *"The
  token half arrives with the design system."* It arrived; the module moved to sit
  beside the tokens it now reaches, gained the seven resource statuses and their
  shapes, and its tests moved with it.
- **`console/visual/baselines/runs.png` changed.** The root layout now carries the
  token stylesheet, so the run list inherits the base layer's ground colour and
  type. Its acceptance record already says the screen has no design reference and
  is expected to be replaced; the new baseline is that change, reviewed as a
  commit.
- **`@testing-library/user-event` was added.** The keyboard claims in this feature
  — tab order, arrow keys through a tab list, space on a switch, escape out of an
  overlay — are tested by pressing keys rather than by asserting that a handler
  exists, and firing raw events by hand would have been a worse version of the
  same library.
- **The unit runner now enables `runScripts: 'dangerously'`.** Solely so the
  no-flash script can be run the way a browser runs it. The alternative was
  `new Function`, which the lint configuration correctly rejects and which would
  have tested a copy of the script rather than the script.

## 15. Test-first sequencing

Followed per module, for the reason features 020, 021 and 033 all give: a suite
written against modules that do not exist can only fail on `ImportError`, which
proves nothing.

The contrast test was written and confirmed red against a missing token table,
then iterated against real values until it passed **without a threshold being
loosened**. The design-literal fixture was watched failing lint on all four kinds
of literal before the rule was believed. The component tests were written per
family and confirmed red before each family existed; three of them stayed red
against real defects (§12) rather than against missing modules, which is the
outcome the ordering exists to produce.

## 16. Gate

`make verify` green: **9,743 passed, 20 skipped**, in 3m38s — lint, format,
mypy, seven import contracts, thirteen guard checks, and the console half in full:
the lockfile, format, lint (including the design-literal rule and the stylesheet
scan), types, 293 unit tests at 98% statements / 92% branches / 96% functions
against a floor of 90, the API client drift check, the standalone production
build, both bundle budgets, ten browser tests against the committed dataset, and
seven visual comparisons inside the pinned container image.

The working tree is clean afterwards. Of the 9,743, 22 are this feature's own
Python contract tests; the 293 console tests and the 10 browser tests are run by
the console gate rather than by pytest.
