# Design

The design references this console is built against, extracted from the boards
they were drawn on and committed here so a code search can reach them.

They were only ever published as Artifacts before, which meant the decision that
governs every chip in the product lived somewhere no `grep` would ever find. It
cost an afternoon: a reader compared the console against a mockup that a later
board had deliberately retired, concluded the code had drifted, and was about to
have it "fixed" back.

Each directory is one board. A `canvas.json` holds the artboard list and the
notes written beside them — read it first, the notes carry the reasoning. A
directory with a single `index.html` was a page rather than a canvas.

Open any file in a browser. They are self-contained: their own tokens, no
network, and they resolve in light, dark and system themes.

## What is here

| Directory | What it decides | Drawn |
|---|---|---|
| `console-redesign/` | **The status vocabulary.** `StatusStyle.html` is the one below. | 2026-08-26 |
| `concept-board/` | Nine concepts translated into this console's vocabulary — investigations open in place, the evidence chip, memory that becomes strategy. | 2026-08-26 |
| `console-audit/` | What the agent screens showed against what they should. | 2026-08-26 |
| `dezenove-telas/` | Nineteen screens read as one system. | 2026-08-12 |
| `proposta-interface/` | The first whole-interface proposal. | 2026-08-10 |
| `settings-v6/`, `settings-v5/` | The settings reorganisation, in two passes. | 2026-08-16, 08-14 |

## The status chip, and the reference it retired

`console-redesign/StatusStyle.html` is titled "Status, four ways". It presents
four directions and marks one **Chosen**:

> **B · Soft pill** — "Still a chip, but one carrier instead of three: a tint,
> no stroke, full radius, sentence case."

That is what the console renders today, and the marks are the board's own:
`Critical` a square, `Investigating` a rotated square, `Completed` a dot,
`Pending` and `Unknown` a **ring**, `Absent` a dash. The shape is the second
carrier of meaning — the board's words: "roughly one man in twelve needs it."

The same board carries a block called **"What is being replaced"**, and what it
replaces is the uppercase bordered tag still drawn in
`console/visual/mockups/04-screen-incident.png`. Its reasons, verbatim:

> Every state is equally loud, so fifty criticals read as wallpaper and the two
> that matter do not surface.
>
> A bordered box around a bordered glyph is a box inside a box.
>
> A 4-pixel radius on a 20-pixel object reads as a legacy tag control rather
> than a chip.

**`04-screen-incident.png` is still `status: "baselined"` in
`console/visual/screens.json`.** Two accepted references disagree, and nothing
in that registry records that the second retired the first. Until it does, the
next reader will make the same wrong comparison.

## Committing these is the point

A design decision nobody can find is a design decision that gets re-litigated.
The repository rule is that everything except a credential may be committed, and
these carry no credential: they are self-contained pages of tokens and markup.

Nothing under `console/` links here, and nothing here is generated. These are
references a person reads, not inputs to a build — the console's own baselines
in `console/visual/` remain what the visual gate compares against.
