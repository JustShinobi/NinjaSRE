# ADR 0014 — A design reference is a committed artefact, and need not be a picture

- **Status:** Accepted
- **Date:** 2026-08-15
- **Constitution impact:** Article XII, Article XIII

## Context

The console records what each screen was reviewed against.
`console/visual/screens.json` registers every screen the visual suite captures,
and each screen marked `baselined` carries an acceptance record naming the design
reference it was first compared to.
`tests/contract/console/test_console_visual_coverage.py` holds the accounting
around it: a reference that arrives and is not registered fails by name, a
reference marked baselined must be claimed by a screen, and a baselined screen
must have both a committed baseline and an acceptance record.

Two properties of that mechanism are load-bearing and correct: it reads committed
files only, so it holds on every machine and in every job; and it makes "the
console matches the design" a claim somebody made rather than an intention
nobody recorded.

Two others have not aged well.

**A reference must be a PNG.** The coverage suite discovers references with a
glob over `*.png`. That was a reasonable reading of "design reference" when the
references were exported comps. It is now a constraint on the *medium*: a design
delivered as a single self-contained HTML document — navigable, showing real
states, responding to the theme — is a better reference than a flat export, and
the registry rejects it purely on file extension.

**A reference may live where the repository cannot see it.** Designs drawn for an
area rework are produced inside planning directories that are deliberately not
committed. A reference there cannot be registered, because a committed file must
not depend on an uncommitted one. The practical result is that the design an area
was actually built against evaporates when the planning directory does, and the
screens it produced are baselined against nothing.

The current numbers show where that leads: of 32 baselined screens, 11 name a
design reference and 21 rest on prose alone. The prose is not a defect — some
screens have no comp and never will — but two thirds is past the point where the
fidelity claim means much, and the mechanism that produced it is the two
constraints above rather than anybody's neglect.

## Decision

**A design reference is any committed, self-contained document the registry can
name and a reviewer can open. It lives in `console/visual/mockups/`, and a design
that a surface was built against is committed there when that work lands.**

1. **Medium.** A reference is a PNG or a single-file HTML document. HTML is
   admitted because it carries states, themes and interaction that an export
   cannot, and because it is what area designs are actually drawn as. It must be
   self-contained — no external stylesheet, script, font or image — so that
   opening it years later shows what the reviewer saw.
2. **Location.** References live in `console/visual/mockups/`. A design in an
   uncommitted planning directory is a working document, not a reference, and
   nothing may be accepted against it.
3. **Promotion.** When work built against a design lands, that design is
   committed as a reference and the screens it produced record their acceptance
   against it. A surface does not reach `baselined` on prose while the drawing it
   was built from exists somewhere uncommitted.
4. **Ownership.** Every reference names the surface it describes, so a reference
   and the screens claiming it can be checked against each other.
5. **Prose stays, and is classified.** A screen with no drawing keeps its written
   acceptance, and names the reason from a closed set rather than supplying free
   text of sufficient length, so the size of the unreferenced set is a number the
   suite can report instead of something only a reader of every record knows.

The coverage suite changes with it: the discovery glob widens to the admitted
media, and a reference in an unsupported format fails by name rather than being
skipped silently.

## Rationale

**The registry was enforcing a file extension while intending to enforce a
review.** Nothing about the acceptance record depends on the reference being
raster. Widening the medium costs one glob and gains the format designs are
actually delivered in.

**A reference that is not committed cannot be a reference.** This is not a new
rule; it is the existing one applied. A record pointing at a path a cloner does
not have is a claim that cannot be checked, which is the failure the coverage
suite was written to prevent — reintroduced through the back door of where the
file happens to sit.

**Promotion is the step that was missing.** Designs get drawn, work gets built
against them, and the drawing is then discarded with the planning material. The
screens survive and the reference does not, so the next reviewer compares the
screen to itself. Committing the drawing when the work lands costs one file and
is the only moment at which somebody still knows which drawing it was.

**Counting the unreferenced set is worth more than shrinking it dishonestly.**
Forcing a reference onto every screen would mean inventing comps for the sign-in
page and the generated galleries. Naming the *kind* of gap instead turns twenty-one
invisible records into a reportable number, which is what lets somebody decide
whether it matters.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep PNG-only and export the HTML designs | An export loses the states, themes and interaction that make the design legible, and produces a picture nobody will regenerate when the design changes. |
| Let the registry reference a path in a planning directory | Breaks the rule that a committed file must not depend on an uncommitted one, and the reference disappears when the planning material does. |
| Require a design reference for every screen | Some screens have no comp and never will; the requirement would be met by inventing references, which is worse than a named gap. |
| Drop the acceptance record and rely on regression alone | Leaves fidelity as an intention nothing holds, which is the state the coverage suite exists to prevent. |
| Keep designs in the planning directory and copy facts into the record | A prose summary of a drawing is not something a later reviewer can compare a screen against. |

## Consequences

**Positive**

- Designs are delivered in the medium they are drawn in, and reviewed in it
- The drawing an area was built against outlives the work that consumed it
- The unreferenced set becomes a reported number rather than a property of the
  file nobody reads
- The rule that a committed file stands on its own is applied where it was being
  quietly bypassed

**Negative**

- HTML references must be kept self-contained, which is a constraint on whoever
  exports them
- Committing a design adds a step at the end of work that currently has none
- Some existing screens will move from "accepted on prose" to "accepted against
  a reference" only when somebody goes back and does it

**Mitigations**

- Self-containment is checkable, and a reference that reaches outside itself can
  fail the coverage suite by name rather than by a reviewer noticing
- Promotion happens once per design, at the moment the work lands, which is when
  the drawing is still identifiable
- The classified prose reasons mean the backlog is visible and can be worked down
  deliberately instead of all at once
