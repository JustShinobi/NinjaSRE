# ADR 0012 — A design-fidelity acceptance expires

- **Status:** Proposed
- **Date:** 2026-08-15
- **Constitution impact:** Article XII

## Context

The console has two visual gates, and they answer two different questions.

**Regression.** `console/tests/visual/screens.spec.ts` walks every screen the
registry marks `baselined`, sets the declared viewport and theme, navigates, and
compares the rendered page to a committed PNG. The comparison is
`toHaveScreenshot` with `maxDiffPixels: 0`, resolved through
`snapshotPathTemplate: 'visual/baselines/{arg}{ext}'`, run inside one pinned
container because font rasterisation differs between machines. This gate is
strong and its answer is exact: *has this screen changed since somebody accepted
it?*

**Fidelity.** `tests/contract/console/test_console_visual_coverage.py` holds the
accounting around that: a design reference committed to `console/visual/mockups/`
must be registered, a reference marked baselined must be claimed by a screen, and
a screen marked baselined must have both a committed baseline and an acceptance
record. It reads committed files only, so it holds on every machine and in every
job.

What the second gate deliberately does not do is compare a baseline to a design
reference. It cannot: one is a full-page screenshot of a running application, the
other is a design comp, and no threshold loose enough to pass them as equal is
tight enough to mean anything.

So fidelity rests entirely on the acceptance record — a claim, made once by a
person, that a screen was reviewed against a named reference. The suite checks
that the claim *exists*. Nothing checks that it is still true. The module's own
docstring is explicit about the scope: the first acceptance is a review, and
every one after it is ordinary visual regression.

That was a sound trade when the design and the screens were young together. It
has three consequences that grow with the repository:

1. **Drift from a design that has since moved is invisible.** A reference can be
   redrawn and every screen accepted against it stays green, because the only
   thing being compared is the screen against its own past.
2. **The unreferenced set is uncounted.** A screen may be accepted with no
   reference at all, on prose alone; the suite requires only that the prose
   exceed forty characters. That is a deliberate escape hatch for screens no comp
   was ever drawn for, and it is also the widest hole in the claim.
3. **An acceptance survives the screen it described.** When a screen is rebuilt
   at the same registry id, its acceptance record carries over unchanged and
   keeps naming a reference drawn for its predecessor.

Measured against the registry as it stands: 37 screens registered, 32 baselined
and 5 pending; of the 32 baselined, 11 name a design reference and 21 rest on
prose alone.

## Decision

**An acceptance record states when it was made and what it was made against, and
the gate fails it when either has moved since.**

Four changes, all of them to committed data and to the suite that already reads
it:

1. **`accepted.at`** — the ISO date of the review.
2. **`revised`** on each entry in the registry's `mockups` list — the ISO date
   that reference was last redrawn.
3. **A baselined screen whose named reference carries a `revised` later than its
   own `accepted.at` fails, by name**, until somebody re-reviews it and moves the
   date. Redrawing a design therefore invalidates exactly the screens that were
   accepted against the older drawing, and nothing else.
4. **`accepted.route`** — the address that was reviewed. A screen whose current
   `route` differs from the one in its acceptance record fails, because the
   record describes a page at an address that no longer serves it.

And one change to the escape hatch:

5. **A screen accepted with no reference names its reason from a closed set**
   rather than supplying free prose of sufficient length. The prose stays, and is
   still required; what changes is that the *kind* of gap becomes a value the
   suite can count and report — a screen with no comp drawn, a screen derived
   from another screen already accepted, a screen generated from the design
   system rather than drawn.

All of it reads committed files. None of it needs the toolchain, a browser, or a
container, which is the property that makes the existing coverage suite runnable
everywhere and is worth keeping.

## Rationale

**A review is a claim about a moment, and a claim with no date cannot go stale.**
That sounds like a convenience and is precisely the defect: the record is written
in the tense of "this matches", when what a person can honestly attest is "this
matched, on this day, against this drawing".

**The two gates should fail for different reasons.** Regression already fails
when the screen moves. Nothing fails when the *design* moves, so the design is
the half of the pair that can drift silently — and the design is the half a
reviewer is least likely to re-read unprompted.

**Twenty-one of thirty-two is the number that matters.** The old-reference
problem is real but bounded to eleven screens. The larger gap is the two-thirds
resting on prose, which today is invisible: there is no way to ask the repository
how much of its fidelity claim is backed by a drawing without reading every
record. A closed reason set turns that into a count.

**The cost is a date in a file somebody is already editing.** An acceptance is
already a reviewed commit. Adding when and against-what to it is not new process;
it is writing down what the reviewer already knew at the moment they accepted.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Compare baselines to references automatically | Different artefacts, different dimensions, different content. A threshold permissive enough to pass proves nothing; a strict one fails everything. |
| Require a design reference for every screen | Some screens have no comp and never will — the sign-in page, the generated design-system galleries. Forcing a reference would mean inventing one, which is worse than admitting the gap. |
| Re-review everything on a schedule | Nothing records that it happened, which is the state this ADR is describing. A calendar is not a gate. |
| Leave it as regression-only | Leaves "the console matches the design" as an intention that nothing holds — the exact failure the coverage suite was written to prevent, reintroduced one level up. |
| Version the whole design set, not per reference | Redrawing one screen would invalidate every acceptance in the repository, so the gate would be routinely overridden, and a gate that is routinely overridden is advisory. |

## Consequences

**Positive**

- The fidelity claim acquires a lifetime, and an expired one is a named failure
  rather than a silence
- Re-review is demanded exactly when the design moved or the address changed, and
  not otherwise
- The screens resting on prose become countable, so the size of the gap is a
  number somebody can decide about
- An acceptance carried across a rebuild stops being inherited silently

**Negative**

- Redrawing a reference makes every screen accepted against it fail until
  re-reviewed. That is the point, and it is still work that lands at a moment
  nobody chose
- The dates are maintained by hand, so a wrong date is a wrong claim
- Migration touches all 32 existing acceptance records

**Mitigations**

- The failure names the screen, names the reference, and says the acceptance is
  older than the drawing, so the required action is in the message
- A date is only ever written in the same reviewed commit as the acceptance it
  describes, which is where a reviewer is already looking at both
- Migration is mechanical for the eleven referenced screens — their `at` is the
  date of the commit that accepted them — and is a one-time classification for
  the twenty-one that rest on prose
