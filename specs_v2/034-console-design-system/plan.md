# Plan — 032 Console Design System

## Technical context

| Concern | Choice |
|---|---|
| Language | TypeScript, strict |
| Styling | Tailwind CSS with a token-only theme; no arbitrary-value classes |
| Primitives | Headless accessible primitives, styled in-repo; no opinionated third-party theme |
| Icons | One outline icon set, imported per-icon so the bundle is tree-shaken |
| Gallery | A route inside the console app itself, excluded from production navigation |
| Contrast proof | A TypeScript port of the existing WCAG arithmetic, run as a unit test over the token table |

## Constitution Check

| Article | Bearing on this feature | Compliance |
|---|---|---|
| VIII — Layered architecture | The console is a surface. It holds no domain logic and imports nothing from `core/` or `platform/`. | The design system is presentation only; it has no knowledge of runs, episodes, or config. |
| X — Operator owns their data | No asset may be fetched from a third-party host at runtime. | Fonts, icons and styles are bundled and served by the deployment. No CDN, no external font. |
| XII — Test-first | Contrast, lint rules and gallery coverage are tests before they are code. | The token table's contrast test and the no-literals lint rule land before the tokens they police. |
| XIII — Language | British English in prose, no attribution to prior art. | Naming is descriptive; no upstream project appears anywhere. |

## Architecture decisions

**Tokens are data, not CSS.** The token table lives in a TypeScript module and is
the single input to three consumers: the Tailwind theme, the runtime CSS custom
properties, and the contrast test. A token added in one place appears in all
three or the build fails.

**Semantic roles sit between status and colour.** Nothing maps a run status
directly to a hue. Status maps to a role (`success`, `warning`, `danger`, `info`,
`neutral`), and the role maps to a token pair. Two screens cannot disagree about
what "degraded" looks like because neither of them decides.

**The gallery is the contract.** Every primitive is registered in the gallery,
and the visual regression suite screenshots the gallery rather than the product
pages. A primitive that is not in the gallery is not covered, and the coverage
test says so by name.

**No literals, enforced mechanically.** A lint rule rejects hex colours, `px`
spacing outside the scale, and raw durations in console source. This is the only
mechanism that keeps a design system from decaying into suggestions.

## Phases

1. **Tokens and themes.** The token table, the contrast test, the Tailwind theme
   generation, the runtime theme switch with no flash on load.
2. **Lint and gate.** The no-literals rule, wired into the console lint config
   and failing on a seeded violation fixture.
3. **Foundational primitives.** Button, Link, Badge, StatusDot, Card, Input and
   the rest of the form controls, each with all declared states.
4. **Composite primitives.** Table, DataList, Tabs, Drawer, Modal, Toast,
   Timeline, DiffView, CodeBlock, and the state components (Empty, Error,
   Skeleton).
5. **Layout primitives and density.** Page header, section, split, width cap, and
   the comfortable/compact switch.
6. **Gallery and audits.** Every variant registered; accessibility audit and
   visual baselines captured; bundle-size budget asserted.

## Risks

- **A design system built without screens is a design system that fits none of
  them.** Mitigated by building 034 and 036 against each other: the primitive
  list above was derived from the screens 034 specifies, and any screen that
  needs something absent adds it here rather than styling locally.
- **Visual baselines are noisy across platforms.** Mitigated by capturing them in
  one containerised browser, pinned, and never on a contributor's machine.
