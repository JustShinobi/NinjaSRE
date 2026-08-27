# Tasks — 033 Console Application Shell

## Phase 1 — Application skeleton

- **T-001** Failing test: every route in the manifest renders with a document
  title naming the page and the deployment.
- **T-002** Next.js application, strict TypeScript, route tree for every area the
  console will carry.
- **T-003** Generate the API client from the gateway's OpenAPI document; fail the
  build when the checked-in client differs from a fresh generation.
- **T-004** Route-level error boundary with retry; test that a thrown page error
  leaves the shell usable.
- **T-005** Not-found route inside the shell, with a way back.

## Phase 2 — Session

- **T-006** Failing test: every route opened unauthenticated renders the sign-in
  and nothing about the deployment. Enumerate from the route manifest.
- **T-007** Sign-in posting to the API origin; cookie exchange in a route
  handler; assert no credential reaches browser-readable storage.
- **T-008** Failing test: three concurrent 401s produce exactly one session end
  and one prompt.
- **T-009** Session controller implementing the single collapse, with
  return-to-route.
- **T-010** Expiry warning before expiry; test the boundary, not the aftermath.

## Phase 3 — Authorisation

- **T-011** Failing role-matrix test: for every role, every nav entry and shell
  control it cannot use is absent from the DOM.
- **T-012** Viewer resolution from the server; presence rule applied to nav and
  shell.
- **T-013** Impersonation banner — persistent, non-dismissible, naming both
  parties. Test it renders on every route.

## Phase 4 — Navigation chrome

- **T-014** Sidebar: grouped areas, icon and label, current marking, collapse to
  drawer below the breakpoint. Test no content is lost at 320px.
- **T-015** Utility bar: deployment name, theme switch, notification centre
  mount, account menu.
- **T-016** PageHeader wired to routes: title, subtitle, breadcrumb, primary
  actions.
- **T-017** Scroll restoration on return to a list; test it survives a round trip
  to a detail page.

## Phase 5 — Palette and notifications

- **T-018** Command registry that areas contribute to; test an area's commands
  appear only when the viewer may run them.
- **T-019** Command palette: keyboard-only operable, navigation plus recent runs
  plus permitted actions, dismiss without side effect.
- **T-020** Notification centre with unread count; test an item resolved
  elsewhere clears without a manual refresh.

## Phase 6 — Internationalisation

- **T-021** Failing completeness test naming any key missing from any locale.
- **T-022** Extract every user-visible string to catalogues; add a lint rule
  rejecting string literals in components.
- **T-023** English and Brazilian Portuguese catalogues; per-key fallback.
- **T-024** Locale-aware dates, durations, numbers; absolute timestamp available
  wherever a relative one is shown.

## Phase 7 — Budgets

- **T-025** Assert the shell renders before page data resolves, with a stalled
  API.
- **T-026** Route transition and first-paint budgets asserted in CI.

## Definition of done

- SC-001 through SC-007 each proven by a named test.
- Role matrix covers every role × every route.
- **Design fidelity.** The shell matches `../_design/03-screen-dashboard.png`
  reviewed side by side: sidebar width and the four nav groups in the documented
  order (Operate · Estate · Learn · Govern), topbar height and contents, page
  header anatomy, the collapse behaviour at each documented breakpoint, and the
  sidebar footer always stating guardian liveness and current posture.
- **Fidelity is judged against fixed data.** The comparison runs against
  feature 032's `populated` scenario — the same anonymised capture the mockups
  were drawn from — so a difference between console and mockup is a difference
  in the console and never in the data.
- **Divergence is allowed and must be recorded** in `deviations.md` with its
  reason, before the feature is called done.
- `make verify` green, console gate included.
