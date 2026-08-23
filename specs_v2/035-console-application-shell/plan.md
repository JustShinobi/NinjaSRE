# Plan — 033 Console Application Shell

## Technical context

| Concern | Choice |
|---|---|
| Framework | Next.js App Router, TypeScript strict, server components where the data is static and client components where it is not |
| API client | Generated from the gateway's OpenAPI document at build time; never hand-written, never a second source of truth about the API |
| Session | Token exchanged for an HTTP-only cookie by a console route handler; the browser never holds the token in readable storage |
| State | Server state through a caching query layer; UI state local; no global store |
| i18n | Message catalogues per locale, keys checked for completeness in CI |
| Palette | A headless command component over a registry the areas contribute to |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| IV — Secrets never reach the agent | The console handles an operator credential. | The credential form posts to the API origin. The console's own storage holds an opaque session, never the token. Integration credentials are never rendered back, only replaced. |
| VIII — Layered architecture | The console is a client of the REST API and nothing else. | No database access, no queue, no direct call into `core/` or `platform/`. The generated client is the only way out. |
| XIV *(governance)* — one implementation | The console must not reimplement a rule the server owns. | Permission decisions come from the server's resolved viewer; the console reads them to decide presence. It never computes a permission. |
| XII — Test-first | Every acceptance scenario is a test first. | Route guards and the 401 collapse are tested before the shell is built around them. |

## Architecture decisions

**Authentication is checked above the router.** One guard, outside every route,
so a route added tomorrow is covered by having been added. This is the property
the Python console got right and the one most easily lost in a file-based router
where each page fetches for itself.

**A 401 is a session event, not a request outcome.** The generated client
publishes it to a single session controller, which ends the session once and
remembers where to return. Three concurrent 401s produce one prompt because they
all reach the same controller, not because each one checks whether another
already handled it.

**Permissions decide presence, not disabled state.** A control the viewer cannot
use is not in the DOM. This is a security-adjacent property — a disabled button
still tells you the capability exists and still ships its handler.

**The token never enters browser-readable storage.** The sign-in posts to the API
origin; the console exchanges the result for an HTTP-only, same-site cookie in a
route handler. Nothing in a component can read a credential, so nothing in a
component can leak one.

**The API client is generated.** The gateway already publishes OpenAPI at
`/openapi.json`. Generating from it means a server-side change that breaks the
console breaks the build, not a screen at three in the morning.

## Phases

1. **Application skeleton.** Next.js app, TypeScript config, generated API
   client, route tree, document titles, error boundaries, not-found.
2. **Session.** Sign-in, cookie exchange, expiry warning, the single-collapse 401
   controller, return-to-route.
3. **Authorisation.** Viewer resolution, the presence-not-disabled rule applied to
   nav and shell controls, impersonation banner.
4. **Navigation chrome.** Sidebar with groups and current marking, responsive
   drawer, utility bar, page header, breadcrumbs.
5. **Palette and notifications.** Command registry, palette, notification centre
   with cross-surface clearing.
6. **Internationalisation.** Catalogues for English and Brazilian Portuguese,
   completeness test, locale-aware formatting, absolute-beside-relative
   timestamps.

## Risks

- **A file-based router invites per-page auth checks.** Mitigated by making the
  guard a layout above every route and adding a test that enumerates the route
  manifest, so an unguarded route fails the suite rather than shipping.
- **Generated clients drift when the generator is run by hand.** Mitigated by
  generating in the build and failing when the checked-in client differs.
