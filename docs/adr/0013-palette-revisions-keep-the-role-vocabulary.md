# ADR 0013 — A palette revision changes values, never the role vocabulary

- **Status:** Accepted
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

A first reading of the revision measured five of its values below the floor,
including its accent. That reading was wrong, and the error is worth recording
because it is easy to repeat: the revision declares **two** greens — a bright one
and a darker one — and the first measurement compared the bright one against the
floor for *text*. The revision uses the bright green for grounds and the dark one
for type. Measured in the role each was drawn for, they pass.

What the revision genuinely lacks is roles, not quality. It declares one value
for states that need both a type and a ground variant, and it has no
`info`, no `neutral`, no foreground for a filled chip, and no `border-strong` —
the role that answers the 3:1 boundary rule, which its hairline border does not
and is not meant to.

None of that is a defect in the drawing. A design comp shows the states the
screens it depicts actually use; the roles it omits are the ones those screens
never needed. Treating a comp as a complete palette is what turns an omission
into a deletion.

## Decision

**A palette revision supplies new values for the roles that already exist. It
may not change the vocabulary, and it is adopted only once the contrast suite
passes on the new values.**

Concretely:

1. The 26 roles and the light/dark pairing are the interface. A revision that
   omits a role is incomplete rather than smaller, and the missing values are
   derived before adoption, not after.
2. **`accent` and `success` stay separate roles, whatever values they carry.** A
   revision may give them the same colour — the first adopted one does, and that
   was a deliberate choice made with a primary button and a success chip shown
   side by side. What must not happen is the two collapsing into a single *role*,
   because then telling interaction apart from state later becomes a sweep of
   every screen instead of two lines in the table. Where they do share a value,
   the thing that has to carry the difference is form — a filled control against
   a tinted chip — and that is a property of the components, not of the palette.
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

**Contrast is measurable, so it should be argued with numbers — and the numbers
have to come from the suite, not from a reviewer's own arithmetic.** The suite
computes every pair from the tokens, in the role each value actually occupies.
A hand measurement does not, which is how the first reading of this revision
concluded its accent failed: the number was right and it was the wrong pair. A
gate that reads the table cannot make that mistake, and it turns "this green is
a bit light" into a pair, a ratio and a floor that a designer can act on in one
pass.

**The change is cheap where it looks expensive and expensive where it looks
cheap.** Re-tokenising the application is one file. The real cost is the human
re-review of every visual baseline, which is why clause 5 makes that a planned
batch rather than a surprise arriving inside an unrelated feature.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Adopt the revision's fifteen values as the whole palette | Would delete `info`, `neutral`, every `on-` foreground and `border-strong` — roles the drawn screens never needed and other screens do. The values were adopted; the vocabulary was not narrowed to fit them. |
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
