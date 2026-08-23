# Tasks — 034 Console Data Surfaces

## Phase 1 — Shared building blocks

- **T-001** Failing test: a panel whose fetch rejects shows its own error and
  retry while sibling panels still render.
- **T-002** Panel boundary component with scoped error and retry.
- **T-003** Empty / loading / error trio wired to every panel; a test that a
  panel with no declared empty state fails the suite.
- **T-004** URL state binding helper; test that filters and selection round-trip.
- **T-005** List virtualisation contract with a stable row height; benchmark on
  ten thousand rows.
- **T-006** Bounded payload viewer for large capability results, expandable, with
  raw retrieval.

## Phase 2 — Runs

- **T-007** Failing benchmark: ten thousand transcript events within budget, plus
  a scaling assertion that cost does not grow with length.
- **T-008** Transcript component covering every event kind — reasoning, call,
  result, evidence, sub-agent dispatch and return, guardrail, interaction,
  report — each visually and semantically distinct.
- **T-009** Structural test: exactly one component renders transcript events.
- **T-010** Run list with filters, sort, and URL state.
- **T-011** Run detail: header, transcript, cost and token breakdown by model and
  turn, links to resources and incident.

## Phase 3 — Dashboard

- **T-012** Attention items panel; each entry reaches its subject in one click.
- **T-013** Summary figures with period, previous-period comparison and
  drill-down; test that a figure without drill-down cannot be rendered.
- **T-014** Activity feed with relative timestamps, absolute on hover or focus,
  icon and label per kind.
- **T-015** Estate summary panel reading from feature 038's data, degrading to an
  empty state when the estate is unpopulated.

## Phase 4 — Memory, knowledge, topology

- **T-016** Episode browse, search and filter; link to the producing run.
- **T-017** Strategy view with supporting episodes and anti-patterns; edit where
  permitted.
- **T-018** Knowledge base browse and search; agent-proposal review queue.
- **T-019** Topology graph with blast radius; keyboard operable; list-equivalent
  view; bounded neighbourhood with a two-hundred-dependent case.

## Phase 5 — Configuration and governance

- **T-020** Failing benchmark: five hundred config nodes within budget, every
  node present.
- **T-021** Org tree and effective configuration with per-value provenance.
- **T-022** Server-backed preview and diff; contract test asserting the preview
  equals the saved effective result and provenance against a real gateway.
- **T-023** Locked, required and approval-gated fields visually distinct, each
  saying what happens on save.
- **T-024** Approval queue grouped by urgency, full decision context, decide in
  place, reason required on rejection.
- **T-025** Audit view with filters and export.

## Phase 6 — Catalogue and administration

- **T-026** Capability catalogue with domain, side-effect level, required
  integrations, and per-team enablement.
- **T-027** Integration state, last verification, verify action.
- **T-028** Credential field posting to the API origin; test no stored secret is
  ever rendered back.
- **T-029** Principals, grants, token issuance and revocation, SSO configuration.

## Phase 7 — Cross-cutting proofs

- **T-030** Empty-state test enumerating every screen against an empty
  deployment.
- **T-031** Role matrix: every role × every screen, asserting absence of write
  controls.
- **T-032** Masked-identifier test: restored for an authorised viewer, masked for
  an unauthorised one, decided by the server.
- **T-033** Visual regression baselines for every screen in both themes, at three
  widths.

## Definition of done

- SC-001 through SC-008 each proven by a named test.
- Exactly one transcript component, asserted.
- **Design fidelity, per screen.** Each screen matches its mockup, reviewed side
  by side, against the reasoning in [`design.md`](design.md):

  | Screen | Reference |
  |---|---|
  | Dashboard | `../_design/03-screen-dashboard.png` |
  | Incident detail, proposal card, transcript | `../_design/04-screen-incident.png` |
  | Resources | `../_design/05-screen-estate.png` |
  | Empty, first-run and panel-error states | `../_design/07-states-empty-error.png` |
  | Dark theme | `../_design/08-theme-dark.png` |

  Fidelity means layout, hierarchy, section order, component anatomy and copy
  tone — not the sample data, which is the reference cluster's real state and
  will differ in any other deployment. In particular, and non-negotiably: the
  attention block sits above the statistics; the proposal card carries all eight
  documented fields in the documented order; the "why degraded" panel shows the
  derivation rather than a provider string; and every empty state carries an
  icon, a heading, a sentence and an action.
- **Fidelity is judged against fixed data.** The comparison runs against
  feature 032's `populated` scenario — the same anonymised capture the mockups
  were drawn from — so a difference between console and mockup is a difference
  in the console and never in the data.
- **Divergence is allowed and must be recorded** in `deviations.md` with its
  reason, before the feature is called done.
- `make verify` green.
