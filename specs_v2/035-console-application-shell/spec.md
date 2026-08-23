# Feature 035 — Console Application Shell

- **Wave:** 9 — Console rework
- **Branch:** `feat/035-console-application-shell`
- **Status:** Draft
- **Depends on:** 032, 033, 034

## Summary

The frame every screen sits in: the application itself, its routing, its session,
its navigation, and the handful of behaviours that must be identical on every
page or they will be wrong on some of them.

The shell owns the persistent sidebar, the utility bar, the page header pattern,
the command palette, the notification centre, the impersonation banner, and the
route-level guards. It is where "an unauthenticated visitor sees the sign-in and
nothing else" is enforced once rather than eleven times — the property the first
wave got right and that must survive the rewrite.

## User scenarios

### Primary story

An operator opens the console. A left sidebar carries the areas of the product
with an icon and a label each, the current one visibly current. The top of the
page names where they are and what the page is for. They press a key, a command
palette opens, they type three letters of a run id and are on that run. Nothing
about how they moved required knowing the URL scheme.

Their token expires mid-session. Rather than a wall of failed requests, they get
one clear prompt, sign in again, and land back on the page they were reading.

### Acceptance scenarios

1. **Given** an unauthenticated visitor, **when** they open any route, **then**
   they see the sign-in and nothing about the deployment behind it.
2. **Given** a signed-in operator, **when** any API call answers 401, **then** the
   session ends once, the sign-in is shown with an explanation, and the route
   they were on is restored after signing in again.
3. **Given** a session nearing expiry, **when** the console renders, **then** it
   says so before the expiry rather than after.
4. **Given** a `viewer` role, **when** the shell renders, **then** navigation
   entries they cannot use are absent, not disabled.
5. **Given** an admin impersonating another principal, **when** any page renders,
   **then** the impersonation is unmistakable and cannot be dismissed.
6. **Given** any page, **when** the operator presses the palette shortcut,
   **then** the palette opens over it, is keyboard-only operable, and closes
   without changing the page if dismissed.
7. **Given** a viewport under 768px, **when** the shell renders, **then** the
   sidebar collapses to a reachable drawer and no content is lost.
8. **Given** a deep link to any route, **when** it is opened cold, **then** it
   renders that route directly, with its own title and its own document title.
9. **Given** a route that does not exist, **when** it is opened, **then** a
   not-found page renders inside the shell with a way back.
10. **Given** a page-level failure, **when** it happens, **then** an error
    boundary contains it to the page; the shell stays usable.

### Edge cases

- Permissions revoked while the console is open on a page they granted.
- A session restored from a stale tab after the deployment restarted.
- A locale whose navigation labels are twice as long as English.
- Browser back and forward across a drawer that changed the URL.
- Two tabs, one signing out.
- A very slow API — the shell must render before the data does.

## Requirements

### Functional

**Application and routing**

- **FR-001** The console MUST be a single application with file-based routing, one
  route per area, and deep-linkable state for anything a user would send to a
  colleague — selected run, active filter, open tab.
- **FR-002** Every route MUST set a document title that names the page and the
  deployment.
- **FR-003** Navigation between routes MUST not re-fetch data the shell already
  holds, and MUST not lose scroll position when returning to a list.
- **FR-004** A route-level error boundary MUST contain a page failure without
  taking the shell down, and MUST offer a retry.

**Session and authorisation**

- **FR-005** Authentication MUST be checked before routing, in one place.
- **FR-006** A 401 from any call MUST end the session exactly once, regardless of
  how many calls are in flight, and MUST remember the route to return to.
- **FR-007** The credential form MUST post to the API origin, never to the console
  origin, and MUST never place a secret in a URL, a log, or client storage
  readable by another origin.
- **FR-008** The viewer's permissions MUST be resolved once per session and used
  to decide presence, not merely enabled state, of every control and nav entry.
- **FR-009** Impersonation MUST render a persistent, non-dismissible banner naming
  who is being impersonated and by whom.

**Navigation**

- **FR-010** The sidebar MUST present the product's areas with an icon and a
  label, group them, mark the current one, and collapse to a drawer under a
  declared breakpoint.
- **FR-011** The utility bar MUST carry the deployment name, the theme switch,
  the notification centre, and the account menu.
- **FR-012** A page header component MUST carry title, subtitle, breadcrumb where
  the route is nested, and the page's primary actions.
- **FR-013** A command palette MUST be reachable by keyboard from anywhere and
  MUST offer navigation, recent runs, and the actions the viewer is permitted.
- **FR-014** A notification centre MUST surface items needing attention —
  approvals, agent questions, failed runs — with an unread count, and MUST clear
  an item when it is resolved anywhere else.

**Internationalisation**

- **FR-015** Every user-visible string MUST come from a catalogue. No string
  literal in a component.
- **FR-016** The catalogue MUST support at least English and Brazilian
  Portuguese, and MUST fall back to English per key rather than per locale.
- **FR-017** Dates, durations, numbers and currency MUST be formatted by locale,
  and absolute timestamps MUST be available wherever a relative one is shown.

### Non-functional

- **NFR-001** The shell MUST render before any page data resolves; a slow API
  delays content, never chrome.
- **NFR-002** Route transitions MUST feel immediate — a declared budget, asserted
  in CI on a cold and a warm route.
- **NFR-003** No user-visible string may be missing from the catalogue; a
  completeness test MUST fail on the missing key, naming it.
- **NFR-004** The application MUST function with JavaScript's slow path — first
  paint MUST not require the full bundle.

## Success criteria

- **SC-001** Every route, opened unauthenticated, renders the sign-in and nothing
  else — asserted per route, so a route added later is covered by being added.
- **SC-002** A 401 arriving on three concurrent calls ends the session once and
  produces one prompt.
- **SC-003** For every role in the role order, every navigation entry and every
  shell control the role cannot use is absent from the DOM.
- **SC-004** A deep link to every route renders that route cold, with its title.
- **SC-005** The command palette is fully operable without a pointer.
- **SC-006** The catalogue completeness test passes for every supported locale.
- **SC-007** Route transition and first-paint budgets hold in CI.

## Out of scope

- The content of the pages — feature 036.
- Streaming and live updates — feature 037.
- Single sign-on flows beyond what the API already exposes.
- A mobile application.
