# Plan — 034 Console Data Surfaces

## Technical context

| Concern | Choice |
|---|---|
| Data fetching | The generated API client behind a caching query layer, with per-panel boundaries |
| Long lists | Windowed rendering with a stable row height contract; server pagination where the API offers it |
| Graphs | A layout computed once per data change, rendered as SVG from the design system's tokens, with a list-equivalent view |
| Diffs | A structural diff over the server's preview response, never a client-side merge |
| Charts | Composed from primitives against the token palette; no chart library theme |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | The transcript is where evidence is shown. | Every claim in a report links to the capability call and result that produced it. A conclusion with no evidence renders as such rather than being hidden. |
| III — Read-only by default | Screens present write actions. | Every write control is gated on a server-resolved permission and, where the change is gated, says the change will be queued. |
| IV — Secrets never reach the agent | Credential fields exist on the integrations screen. | The form posts to the API origin, stored secrets are never rendered back, and the field only ever replaces. |
| VIII — Layered architecture | These are surfaces. | No merge, no permission computation, no masking decision happens here; each is the server's answer, rendered. |
| X — Operator owns their data | Export must be possible. | The audit view exports; run traces are retrievable in full. |

## Architecture decisions

**One transcript component, live and replay.** The single most valuable property
the first wave established, and the easiest to lose in a rewrite where a live
view and a history view are two obvious files. The component takes a sequence of
events; whether they arrive from a replay call or a stream is the caller's
problem, and feature 037 is that caller.

**Panels fail alone.** Every region that fetches has its own boundary, its own
error state and its own retry. A dashboard is six independent questions; one
unanswerable question must not blank the other five.

**Empty states are content, not absence.** Each names what would be here and the
action that produces it. This is the difference between a fresh deployment that
looks broken and one that looks new — and given that the first live run of this
system showed empty tables everywhere, it is the highest-leverage requirement in
the feature.

**Server answers, client renders.** Configuration merges, permission decisions,
masking restoration and blast-radius computation all already exist on the server.
None is recomputed here. A client-side merge that agrees with the server today is
a client-side merge that disagrees with it after the next config-service change.

## Phases

1. **Shared building blocks.** Panel boundary, empty/loading/error trio, URL
   state binding, list virtualisation contract, bounded payload viewer.
2. **Runs.** List with filters; detail with the single transcript component;
   cost breakdown; links to resources and incidents.
3. **Dashboard.** Attention items, summary figures with comparison, activity
   feed, estate summary.
4. **Memory, knowledge, topology.** Episode browse and search, strategies with
   anti-patterns, knowledge base with the proposal queue, topology graph with a
   list equivalent.
5. **Configuration and governance.** Org tree, effective config with provenance,
   server-backed preview and diff, approval queue with decide-in-place, audit
   with export.
6. **Catalogue and administration.** Capability catalogue, integration state and
   verify, credential replacement, principals, grants, tokens, SSO.

## Risks

- **Two transcript implementations appear by accident.** Mitigated by a
  structural test asserting exactly one component renders transcript events, run
  before the live layer is built on top of it.
- **The dashboard becomes a wall of numbers.** Mitigated by FR-003: a figure with
  no drill-down may not be shown, which removes most decorative metrics at
  specification time.
- **Graph rendering does not scale.** Mitigated by bounding the rendered
  neighbourhood, with the full set reachable through the list-equivalent view.
