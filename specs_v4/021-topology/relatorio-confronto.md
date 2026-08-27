# 021 Topology — implementation confrontation

Date: 2026-08-13

## Conclusion

Unlike the previous confrontation (020 Resources), the control file here was not
stale in either direction. All three problems `spec.md` names — the two
identical empty panels, the empty state's dead-end door, and the raw `root`
sentinel in the breadcrumb — are genuinely resolved in the current source, and
the fix committed under "onda 3" (`fb80663`, `feat: make five empty states say
why this deployment is empty`) is still in place at HEAD `b5cc3ca`. Reading
`console/src/surfaces/screens/topology.tsx` line by line against each
acceptance criterion, then running the seven tests `controle.md` cites, proved
every claim rather than merely repeating it: all seven pass against the
unmodified tree, and the full console suite (1931 tests, 120 files) is green
alongside a clean `tsc`, `eslint`, and `prettier`. The shared mechanism behind
item 2 (`emptyBecause`/`setupCause` in `console/src/surfaces/emptiness.ts`) is
not local to this screen — it is the same helper eight other screens
(`memory.tsx`, `knowledge.tsx`, `detectors.tsx`, `data.tsx`, `approvals.tsx`,
`proposals.tsx`, `incidents.tsx`, and this one) already call, so a defect in it
would not be invisible the way a screen-local bug can be.

Chasing root causes across tiers — platform's `TopologyGraph` port, its fake,
the `/v1/topology/{node_id}` gateway route, and the demo fixtures — surfaced
two things worth recording but neither one is a defect against any of the
three problems `spec.md` names, and neither is fixed here for that reason:
first, the screen's default node (`'root'`) belongs to the organisation
hierarchy's identifier space (`/v1/config`), not the topology graph's service
identifiers (`svc-ledger` and siblings in the demo data), and nothing in the
console currently links into `/topology?node=<a real service id>` — so the
unqualified address is empty even on a populated deployment, reachable to a
real node only by hand-editing the URL or clicking through an already-open
graph. Second, `gateway/http/routes/topology.py`'s `get_topology` never
actually returns HTTP 404 (`platform/persistence/fakes/topology_graph.py`'s
traversal methods return empty results rather than raising for an unseen node,
and the route has no other path to a 404), while
`fixtures/scenarios/empty/topology.json` and
`fixtures/scenarios/first-run/topology.json` declare status 404 for the same
condition. Both are pre-existing, both are outside what `spec.md`'s three
problems and two acceptance criteria ask for, and both are named here rather
than left silent, per the two subsections below and the note added to
`controle.md`.

No code was changed. No new test was written, because no gap was found for one
to pin — the seven existing tests in `topology.test.tsx` already assert
exactly what the two acceptance criteria require, and they were run (not just
read) to confirm that.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Two panels, the same empty, side by side | FEITO (onda 3) | Confirmed accurate. `topology.tsx:126-133` renders exactly one `Panel` when `resolvedState === 'empty'`; the two-panel grid (`:134-231`) only renders once dependencies or dependents exist. Both directions covered by `topology.test.tsx` and passing. | DONE (no change) |
| 2. The empty state hides the real dependency | FEITO (onda 3) | Confirmed accurate. `emptyBecause(..., setupCause(locale, setup))` (`topology.tsx:103-112`) replaces the heading's body and action with the setup cause while steps are outstanding, and falls back to the original mechanism text once setup is complete — the same helper eight other screens share. Covered by three tests in `topology.test.tsx`, passing. | DONE (no change) |
| 3. Breadcrumb "Topology > root" | FEITO (onda 3) | Confirmed accurate. `DEFAULT_NODE = 'root'` (`topology.tsx:48`) is never printed: the crumb reads the organisation's own name from `/v1/config` at the unqualified address (`:115-120`), or is omitted when that name cannot be resolved, because `trailFor` draws no breadcrumb for a trail of one (`shell/routes.ts:435-437`). Covered by three tests in `topology.test.tsx`, passing. | DONE (no change) |

## Evidence

### 1. Two panels, the same empty, side by side

`console/src/surfaces/screens/topology.tsx:89-90` computes emptiness from the
parsed body rather than from a status code:

```ts
const empty = dependencies.length === 0 && dependents.length === 0;
const resolvedState = stateOf(topology, empty);
```

`:126-231` branches on that single value: `resolvedState === 'empty'` renders
one `Panel` titled "Neighbourhood" and nothing else; any other state (`ready`
or `error`) renders the two-column grid with the picture (`DependencyGraph`)
on the left and the list (`graph-list`) on the right. There is no code path
left that can print two `empty`-state panels — the ternary at `:126` is the
only place `PanelState` decides how many `<Panel>` elements exist, and it is
binary.

`console/tests/unit/surfaces/topology.test.tsx:136-142`
(`'draws one empty state, not a matched pair'`) asserts `panels()` has length
1 and `data-state="empty"` when the setup checklist is incomplete;
`:174-186` (`'splits into the picture and the list once there is
something to split'`) asserts length 2, both `data-state="ready"`, and both
`graph`/`graph-list` present once `TOPOLOGY_WITH_DATA` is served. Both were run
against the current tree and pass (`Test Files 2 passed (2)`, see
Verification).

I looked for the one case these two tests do not exercise directly — a
dependency read that genuinely fails (`resolvedState === 'error'`) — because
that also takes the two-panel branch, and confirmed it is not the case this
item is about. The acceptance criterion reads "**Sem dados**, a página mostra
um único empty state" (without *data*, not without a *successful read*), and
the problem statement's own repro is specifically the two `"No topology
recorded"` panels, not two error cards. Two independent `ErrorState` blocks —
each named, each with its own retry — is the console-wide "panels fail alone"
convention (`console/AGENTS.md`: "each panel also has its own error boundary
and its own retry... one unanswerable question must not blank the other
five"), not a duplicate of this item's defect. No change needed here.

### 2. The empty state hides the real dependency

`console/src/surfaces/screens/topology.tsx:100-112`:

```ts
// Investigations feed the graph and cannot run before the setup they need
// is finished, so an unfinished checklist — not "nothing has been observed
// yet" — is why this deployment's neighbourhood is blank.
const cause = setupCause(locale, setup);
const emptyState = emptyBecause(
  {
    heading: message(locale, 'topology.empty.heading'),
    body: message(locale, 'topology.empty.body'),
    actionLabel: message(locale, 'topology.empty.action'),
    href: '/resources',
  },
  cause,
);
```

`setupCause` (`console/src/surfaces/emptiness.ts:45-53`) returns `null` once
`outstanding(setup) === 0`, and otherwise a `Cause` whose body names how many
setup steps remain and whose action links to `/first-run`. `emptyBecause`
(`emptiness.ts:79-87`) keeps the panel's heading and substitutes the body and
action only when a cause applies — which is exactly the causal chain the
problem statement asks for: investigations feed the graph, investigations
need the finished setup, and the empty state names the outstanding step count
and points at `/first-run` rather than at Resources while that gate is closed.
Once the checklist is complete, `cause` is `null` and the screen's own words
return — `"The graph is built from what investigations observe. Nothing has
been observed about this node yet."` (`i18n/en.ts:878-879`) with `"See the
estate"` → `/resources` — which is the accurate statement once the setup gate
is no longer what is blocking the graph.

This is not a topology-local mechanism. `setupCause` is called from
`memory.tsx`, `knowledge.tsx`, `detectors.tsx`, `data.tsx`, `approvals.tsx`,
`proposals.tsx`, and `incidents.tsx` as well — eight screens sharing one
helper, confirmed via `codegraph_explore`'s blast-radius listing for
`setupCause` (`console/src/surfaces/emptiness.ts:45`, 16 call sites). A defect
here would not be specific to Topology.

Three tests in `console/tests/unit/surfaces/topology.test.tsx:144-171` pin
both halves: `'names the outstanding setup, not the estate it does not feed'`
asserts the setup-cause text and the `/first-run` link and explicitly asserts
the original mechanism sentence is **absent**
(`.not.toHaveTextContent('The graph is built from what investigations
observe')`); `'keeps the mechanism explanation once the setup is not what is
blocking it'` asserts the reverse once `SETUP_COMPLETE` is served. Both run
and pass against the current tree.

### 3. Breadcrumb "Topology > root"

`console/src/surfaces/screens/topology.tsx:48-49,63-66,115-120`:

```ts
const DEFAULT_NODE = 'root';
...
const atRoot = nodeId === DEFAULT_NODE;
...
const orgName = atRoot ? (placedTree(dataOf(tree))[0]?.name ?? '') : '';
const nested = atRoot
  ? orgName === ''
    ? []
    : [{ label: orgName }]
  : [{ label: nodeId }];
```

`root` is a sentinel this screen falls back to when the address carries no
`?node=`; it is used only to select which node to query and to decide which
branch computes `orgName`, and it is never interpolated into anything a
viewer reads. At the unqualified address, the crumb is the organisation's own
name, read from `/v1/config` (`:82`, the same `optionalRead` convention
`dashboard.tsx:116`, `first-run.tsx:136`, and `approvals.tsx:193` already use
for `/v1/config/{node_id}`) — or omitted outright when that tree names
nothing, because `AreaHeader` draws no `Breadcrumb` for a trail of one
(`console/src/shell/area.tsx:53`, `console/src/shell/routes.ts:435-437`):
`trailFor` returns a single crumb when `nested` is empty, and `AreaHeader`
only renders the `Breadcrumb` landmark when `trail.length > 1`. That satisfies
the acceptance criterion's stated alternative directly — "exibir o nome da
organização... ou omitir o crumb" — by consistently choosing the first option
whenever the name is available and falling back to the second when it is not.

Three tests in `topology.test.tsx:188-218` cover this: the literal string
`'root'` is never in the document regardless of whether the org tree
resolves (`:189-194`, `:206-217`); the breadcrumb landmark itself is absent
when the tree cannot name anything (`:196-204`); and it reads "Northwind"
— never "root" — once the tree can (`:206-217`). All three run and pass.

**Traced and deliberately left alone**, matching what `controle.md` already
noted: the SVG subject box (`console/src/surfaces/graph.tsx:131-148`,
`data-testid="graph-subject"`) still renders the raw `nodeId` as the centre
node's label. `/v1/topology/{node_id}` never returns a name for the node it
was asked about — `gateway/http/routes/topology.py`'s `TopologyView` only
carries `name` on the *neighbours* it lists (`TopologyNodeView`, `:27-32`),
never on the subject itself — so there is no name to substitute without a
larger change. The acceptance criterion is specifically about the breadcrumb;
this is a different element, and I confirmed it is unreachable from the
breadcrumb's own logic before treating it as out of scope rather than missed.

A second, related observation, new to this confrontation: when a viewer is
*not* at the unqualified address — reached by clicking a dependency,
dependent, or blast-radius entry inside an already-open graph, the only way
`?node=` is ever set to something other than `root` in this console — the
breadcrumb prints that raw `nodeId` too (`:120`,
`[{ label: nodeId }]`), for the identical reason: the endpoint only names
neighbours, never the node the query was centred on. The acceptance
criterion's own wording — "**Nenhum identificador interno (`root`)** em
breadcrumb" — names the one literal string the bug report was about, which
this never prints in either case, at any address. Generalising "no raw
identifier of any kind" to every possible `?node=` would be a materially
larger feature (the topology API would need to be asked to name its own
subject, or the console would need to carry the name forward from wherever
the link was built), and nothing in `spec.md`'s two acceptance criteria or
three problems asks for it. Left alone, named here rather than silently
dropped.

### An adjacent architectural note, not a defect against this spec

Investigating why a populated deployment's topology graph is only ever
reachable by hand-editing the address surfaced that `DEFAULT_NODE = 'root'`
draws from the *organisation hierarchy's* identifier space
(`fixtures/scenarios/populated/topology.json` seeds the demo's org root with
`node_id: 'root'` via `platform/startup/demo/dataset.py:92-95`), while the
topology graph itself is keyed by service identifiers that share no namespace
with it (the same populated fixture's example subject is `svc-ledger`,
confirmed at `fixtures/scenarios/populated/topology.json:75`). A search of
`console/src/` found no screen anywhere that links to `/topology?node=<a real
service id>` — the only in-app way to reach one is to already be looking at a
populated neighbourhood and click into it. That means the unqualified
`/topology` address renders the empty state even on a fully populated,
fully-configured deployment. This is a genuine usability gap, but it is not
one of `spec.md`'s three named problems, and neither acceptance criterion asks
for a node picker or a different default. `controle.md`'s own note that "onda
4 traz a fusão em Knowledge (spec 090)" suggests node selection may belong to
that redesign rather than to a polish pass on this screen's empty states and
breadcrumb. Not fixed here; named so it is not lost.

One more trace worth recording briefly: `gateway/http/routes/topology.py`'s
`get_topology` (`:63-96`) never returns HTTP 404 — an unseen node produces a
normal 200 with empty `dependencies`/`dependents`/`blast_radius`, because
`platform/persistence/fakes/topology_graph.py`'s `direct_dependencies` /
`direct_dependents` / `blast_radius` (`:111-219`) return empty
`TraversalResult`/`BlastRadius` values rather than raising for a node id the
graph has never seen — there is no code path left that raises
`RecordNotFound` for this specific traversal. Yet
`fixtures/scenarios/empty/topology.json` and
`fixtures/scenarios/first-run/topology.json` declare `"status": 404` for the
same condition, and `tools.mockplane` replays that status verbatim (confirmed
against `tests/unit/tools/mockplane/test_server.py:160`, which asserts the
same 404 for a *different* scenario's topology answer). I checked whether this
produces any console-visible defect and it does not: `topology.tsx`'s
`empty` computation (`:89`) is derived from the parsed body's array lengths,
which are `[]` either way — under a 404 (`optionalRead` resolves it to `{}`,
whose `list(..., 'dependencies')` is also `[]`) or under a 200 with genuinely
empty lists, `resolvedState` and everything downstream is identical. No route,
no `response_model`, and no committed OpenAPI document was touched here: this
is a mock/real inconsistency with no observable effect on any of the three
items this spec asks for, and fixing it would touch the generated console API
client for something outside a breadcrumb-and-empty-state polish. Named, not
fixed.

## Verification

Every gate below was run against the tree as it stood at HEAD `b5cc3ca`; no
file was changed during this confrontation, so there is nothing to diff.

Console:

- `pnpm exec vitest run tests/unit/surfaces/topology.test.tsx
  tests/unit/surfaces/tree.test.tsx` — **2 files passed, 15 tests passed.**
  All seven tests `controle.md` cites for this spec are among them.
- `pnpm exec vitest run` (full unit suite) — **120 files passed, 1931 tests
  passed.** One benign jsdom console line ("Not implemented: navigation to
  another Document") is pre-existing test-environment noise, matching what
  the 020 confrontation already recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/screens/topology.tsx src/surfaces/graph.tsx
  src/surfaces/tree.tsx src/surfaces/emptiness.ts src/surfaces/read.ts
  src/i18n/en.ts src/i18n/pt-BR.ts tests/unit/surfaces/topology.test.tsx
  tests/unit/surfaces/tree.test.tsx` — clean.
- `pnpm exec prettier --check` on the same source files (test files
  included, catalogues excluded — prettier does not format `.ts` catalogues
  differently from ordinary source, so they were covered by the lint run
  above) — "All matched files use Prettier code style!"

Python:

- `uv run python -m pytest tests/contract/persistence/test_topology_graph.py`
  — **21 passed, 1 skipped** (the skip is the Postgres-backed case, which
  needs `make test-postgres` and a database; not run here, consistent with
  `AGENTS.md`'s description of that gate).
- `uv run python -m pytest tests/unit/platform/knowledge/topology/` — **26
  passed.**
- `uv run ruff check platform/persistence/ports/topology_graph.py
  platform/persistence/fakes/topology_graph.py gateway/http/routes/topology.py
  platform/knowledge/topology/queries.py` — clean.
- `uv run mypy` on the same four files — clean, no issues found.

Not run: `make test-postgres` (needs a database this environment does not
have; the one skipped test above is the case it would cover) and the browser
suites (`make console-e2e`, `make console-visual`), which need the pinned
toolchain and a running gateway. Neither is implicated by anything found in
this confrontation — no route, no OpenAPI document, and no fixture was
changed.

**On confirming new tests red first:** no new test was written for any of the
three items, because no gap was found that a new test would pin. Instead, the
existing tests that `controle.md` already cites were *run*, not just read,
against the unmodified tree, and all passed — which is what stands in for
red-before-green here: there was no implementation change to precede with a
failing test, and the report says so plainly rather than inferring
correctness from the source alone.

## Control reconciliation

`specs_v4/021-topology/controle.md` is updated to point at this report and to
state that the confrontation re-ran and reconfirmed all three rows rather than
merely re-asserting them. The verdicts themselves are unchanged — all three
were already `FEITO` and remain so — but the detail column now cites the
`file:line` evidence and the tests that were actually executed, and a new note
records the two adjacent, out-of-scope observations (the unreachable default
node, and the fixture/route 404 mismatch) so they are not lost even though
neither is fixed here.
