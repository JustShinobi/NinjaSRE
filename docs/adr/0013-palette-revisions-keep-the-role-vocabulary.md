# ADR 0013 — A palette revision changes values, never the role vocabulary

- **Status:** Proposed
- **Date:** 2026-08-15
- **Constitution impact:** Article XII

## Context

The console's colour is a closed vocabulary of roles rather than a set of
pictures. `console/src/design/tokens.ts` declares 26 colour roles across two
themes — `surface`, `sunken`, `raised`, `hover`, `text`, `muted`, `accent`,
`border`, `border-strong`, the five semantic roles `success`, `warning`,
`danger`, `info`, `neutral`, and for each of those an `-bg` fill and an `on-`
foreground. The module states the property the vocabulary exists for:

> Nothing maps a status to a hue. A status maps to a role and a role maps to a
> token pair, so two screens cannot disagree about what "degraded" looks like
> because neither of them decides.

Two mechanisms hold it. A lint rule makes the token table the only place a
colour may be written, and `console/tests/unit/design/contrast.test.ts` computes
contrast **from the tokens** rather than from a screenshot, requiring 4.5:1 on
every pair a viewer reads text from and 3:1 on every boundary a viewer has to
find, in both themes.

A palette revision has been drawn as part of an area rework. It proposes a
different, greener family, and it is narrower than the vocabulary it would
replace: about fifteen custom properties against twenty-six roles. It has no
`info` and no `neutral`, no `on-` foreground for any filled chip, and no
equivalent of `border-strong`. It gives `accent` and the success colour **the
same value** in both themes.

Measured against the thresholds the contrast suite already enforces, the
proposed values fail in five places:

| Pair | Proposed | Floor |
|---|---|---|
| third text level on panel (light) | 3.86:1 | 4.5:1 |
| **accent on panel (light)** | **4.10:1** | 4.5:1 |
| success on its fill (light) | 3.54:1 | 4.5:1 |
| warning on its fill (light) | 4.36:1 | 4.5:1 |
| third text level on panel (dark) | 4.00:1 | 4.5:1 |

The palette in the tree passes every one of those pairs — 6.09:1 for accent in
light, 5.74:1 and 5.43:1 for success and warning on their fills, 10.43:1 for
accent in dark. Neither palette reaches 3:1 for the hairline border against the
surface, and neither needs to: that rule is met by `border-strong`, a role the
current palette holds at 3.91:1 in light and 6.30:1 in dark, and which the
proposal does not have at all.

So the revision cannot be adopted as drawn, and the reason is not taste. Three
of its five failures are the colours an operator reads a *state* from, and the
one marked in bold is the primary interaction colour of the product.

## Decision

**A palette revision supplies new values for the roles that already exist. It
may not change the vocabulary, and it is adopted only once the contrast suite
passes on the new values.**

Concretely:

1. The 26 roles and the light/dark pairing are the interface. A revision that
   omits a role is incomplete rather than smaller, and the missing values are
   derived before adoption, not after.
2. **`accent` and `success` MUST remain distinct.** Interaction and state are
   different questions, and a palette that answers both with one hex removes the
   operator's ability to tell "press this" from "this is fine".
3. A revision lands as a change to the token table and nothing else. Because the
   lint rule already guarantees no colour is written anywhere else, this is one
   file, and every screen follows without being touched.
4. The contrast suite is the acceptance gate, run before the visual baselines are
   recaptured. A revision that fails it is returned to the designer with the
   failing pairs and their measured ratios, which is a specific request rather
   than an aesthetic objection.
5. Recapturing the visual baselines is the cost of a palette change and is
   planned as one reviewed batch, never absorbed screen by screen.

## Rationale

**The vocabulary is the part that makes screens agree.** Values are a matter of
taste and belong to whoever owns the product's look. The mapping from meaning to
role is not taste: it is what stops two screens rendering "degraded" differently,
and it is the only part of the design system that a new screen inherits for free.

**A drawing cannot know what it omits.** A design comp shows the states it
happens to depict. `info` and `neutral` are absent from the revision not because
somebody decided the product no longer needs them, but because the screens drawn
did not use them. Treating a comp as the complete palette silently deletes roles
that other screens depend on.

**Contrast is measurable, so it should be argued with numbers.** The suite
already computes it from the tokens. Making it the gate turns "this green is a
bit light" into "4.10:1, and the floor is 4.5:1", which a designer can act on in
one pass.

**The change is cheap where it looks expensive and expensive where it looks
cheap.** Re-tokenising the application is one file. The real cost is the human
re-review of every visual baseline, which is why clause 5 makes that a planned
batch rather than a surprise arriving inside an unrelated feature.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Adopt the revision as drawn | Five pairs fail the accessibility floor the suite already enforces, and three of them are state colours. It would also delete `info`, `neutral`, every `on-` foreground and `border-strong`. |
| Adopt it and lower the contrast floor | The floor is the reason the suite is worth running. Moving a threshold to admit a colour is how an accessibility gate becomes decorative. |
| Adopt it only on the screens it was drawn for | Two palettes in one product, decided per screen — precisely the disagreement the role vocabulary exists to prevent. |
| Keep the current palette and discard the revision | Throws away a deliberate design decision over what is, in the end, a set of values that can be re-derived to pass. |
| Let each area own its own accent | Colour would stop meaning anything across the product, and the semantic roles would have to be duplicated per area. |

## Consequences

**Positive**

- A revision becomes a bounded, checkable change: new values, one file, one
  suite, one baseline review
- Design feedback is expressed in measured ratios rather than opinion
- Roles that no comp happens to draw survive a redesign
- Interaction stays distinguishable from state, in both themes

**Negative**

- A designer cannot hand over a palette and have it adopted verbatim; the
  missing roles have to be derived and the failing pairs adjusted
- A palette change invalidates every visual baseline at once
- Deriving `on-` foregrounds and `border-strong` for a new family is real work
  that the comp does not contain

**Mitigations**

- The failing pairs are reported with their measured ratio and the floor, so the
  adjustment is specific and usually small
- The derived roles need to satisfy the thresholds and nothing else, so they can
  be computed and then reviewed rather than designed from scratch
- The baseline recapture is one reviewed commit, scheduled deliberately, and the
  acceptance records it produces carry their own review date
