# Tasks — 032 Console Design System

Test-first throughout: the failing test lands before the implementation and is
confirmed failing.

## Phase 1 — Tokens and themes

- **T-001** Write the failing contrast test over an empty token table, asserting
  every body pair reaches 4.5:1 and every boundary pair 3:1, in both themes.
- **T-002** Port the WCAG relative-luminance and contrast arithmetic to
  TypeScript; assert it against the values the Python implementation produces for
  the existing palette.
- **T-003** Define the colour role table for light and dark. Iterate until T-001
  passes without loosening a threshold.
- **T-004** Define the type, spacing, radius, border, shadow and duration scales
  as closed sets.
- **T-005** Generate the Tailwind theme from the token table; assert the
  generated theme and the table cannot diverge.
- **T-006** Implement theme resolution: system default, explicit override,
  persisted, with no flash of the wrong theme on first paint. Test the no-flash
  property, not just the final state.

## Phase 2 — Lint gate

- **T-007** Write a fixture component containing a hex colour, an off-scale `px`
  value and a raw duration. Assert lint fails on it.
- **T-008** Implement the no-literals lint rule until T-007 passes and the rest
  of the console lints clean.

## Phase 3 — Foundational primitives

- **T-009** Status-to-role mapping module, with a test that an unknown status
  maps to neutral and renders its raw text.
- **T-010** Button, IconButton, Link — all variants, all states, destructive
  variant distinct from accent, keyboard operable, accessible names on icon-only.
- **T-011** Badge, StatusDot — each asserting that colour is never the sole
  carrier.
- **T-012** Card, StatTile — including the loading and empty forms.
- **T-013** Input, Select, Textarea, Checkbox, Radio, Switch, Combobox,
  DateRange — labelled, described, error state, keyboard operable.
- **T-014** Spinner, Skeleton, ProgressBar — each honouring reduced motion by
  removal, asserted.

## Phase 4 — Composite primitives

- **T-015** Table and DataList, including the responsive collapse at 320px and
  the long-single-token cell case.
- **T-016** Tabs, Breadcrumb, Pagination — roles and keyboard patterns asserted.
- **T-017** Drawer, Modal — focus trap, restore on close, escape to dismiss,
  scroll lock.
- **T-018** Toast and Tooltip — announced to assistive technology, dismissible,
  never the only place an outcome is reported.
- **T-019** Timeline, CodeBlock, DiffView — with the very-large-payload case
  bounded.
- **T-020** EmptyState and ErrorState, each requiring a message and an action.

## Phase 5 — Layout and density

- **T-021** PageHeader, Section, SplitLayout, ContentWidth as components.
- **T-022** Comfortable and compact density at the application level; assert only
  spacing and control height change.

## Phase 6 — Gallery and audits

- **T-023** Gallery route rendering every primitive × every variant × every
  state, excluded from production navigation.
- **T-024** Coverage test: every exported primitive appears in the gallery, by
  name. Fails when one is added without registration.
- **T-025** Accessibility audit over every gallery entry; no violations at the
  declared level.
- **T-026** Visual regression baselines for the gallery at 320px, 768px and
  1440px, in both themes, captured in the pinned container.
- **T-027** Theme-parity test: a pixel diff between themes differs in colour
  only, never in geometry.
- **T-028** Stylesheet and icon bundle size budgets asserted in CI.

## Definition of done

- Every task above complete, each with its test.
- SC-001 through SC-006 each proven by a named test.
- The gallery renders and is the visual-regression source.
- **Design fidelity.** The built system matches
  [`../_design/mockups.html`](../_design/mockups.html) and the values in
  [`design.md`](design.md). Specifically: every colour token equals its
  documented value to the byte; the type, spacing, radius and duration scales are
  exactly the closed sets documented, with no additional step; every status
  carries the documented shape as well as its colour; and each primitive's
  anatomy matches `01-tokens-colour.png` and `02-tokens-scales.png` reviewed side
  by side.
- **Fidelity is judged against fixed data.** The comparison runs against
  feature 032's `populated` scenario — the same anonymised capture the mockups
  were drawn from — so a difference between console and mockup is a difference
  in the console and never in the data.
- **Divergence is allowed and must be recorded.** Where the built component
  differs from the mockup, the difference and its reason go in `deviations.md`
  before the feature is called done. An undocumented divergence is a defect, not
  a judgement call.
- `make verify` green, including the console gate from feature 033.
