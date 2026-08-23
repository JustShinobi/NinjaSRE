# Deviations — 050 Two broken screens

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. The resolver takes a read view state and a placed tree, not a search string

**Planned.** `plan.md`: "a small helper `resolveNode(search, filters, viewer,
tree)` in `console/src/surfaces/url-state.ts`".

**Done.** `resolveNode(state: ViewState, viewer: NodeHolder, nodes: readonly
NodeCandidate[]): string`, in that file, beside `readViewState`. The payload
half became a second helper, `placedTree(payload: unknown)`, in
`console/src/surfaces/tree.tsx`.

**Why.** The planned signature does two jobs the module's own docstring says it
does not do. `(search, filters)` is `readViewState(search, filters)` — every
caller already has the result, and passing the raw pair would mean reading the
address twice per render. `tree` as a raw `/v1/config` payload would put payload
parsing in a module whose first line is "Pure functions over a query string";
url-state.ts imports nothing today and still imports nothing.

Splitting it also removed the duplication the plan was aiming at. Configuration
was mapping `nodes` → `node_id`/`name`/`kind`/`parent_id` inline, and the two
screens being fixed would each have had to grow a copy. `placedTree` is that
mapping, once, and it answers emptiness once too: a payload from a read that
failed arrives as `undefined` and comes back as an empty tree rather than a
throw.

Both parameters are typed structurally (`{ teamNodeId: string }`,
`{ id: string }`) rather than as `Viewer` and `PlacedNode`, so url-state.ts
gained no imports at all.

<!-- proof: console/tests/unit/surfaces/url-state.test.ts -->
<!-- proof: console/tests/unit/surfaces/tree.test.tsx -->

---

## 2. Configuration's fallback order changed, and three screens now share one rule

**Planned.** `plan.md` gives configuration as the pattern to copy — "`?node=` →
root" — and gives autonomy a different one: "`node ?? (teamNodeId || root) ??
''`". It then says the rule must not fork.

**Done.** One order, everywhere: the address, then a non-empty
`viewer.teamNodeId`, then the root of the tree, then `''`. Configuration adopted
it, which inserted the viewer's team ahead of the tree root for that screen.

**Why.** Those two orders are the fork the plan says not to have, and shipping
both would have meant `/configuration?` and `/autonomy?` landing on different
nodes for the same person, for no reason a reader could see. One of them had to
give, and the viewer's own team is the better default on both: it is the part of
the deployment the person is responsible for, and the root is a fallback for
when nobody has one.

**What it cost.** Under every fixture the suite carries, nothing: the dataset's
principal's team node is also the root of the committed tree, so `placed[0].id`
and `viewer.teamNodeId` are the same string. All console unit tests, 60 browser
tests and 20 visual baselines pass unchanged. Where it would differ is a
deployment whose operator belongs to a team below the root — and there the new
answer is the useful one.

**The one ordering decision worth stating.** The viewer's team is consulted
*before* the tree, not after. The tree read is its own panel and fails on its
own; a screen that lost its subject because the node *selector* was unreachable
would turn one dead region into a dead page, which is the exact failure this
feature exists to remove.

<!-- proof: console/tests/unit/surfaces/url-state.test.ts -->

---

## 3. Catalogue's capability panel now reports its second read's failure

**Planned.** Nothing asks for this. `plan.md` says the `/v1/capabilities` and
`/v1/integrations` panels are node-free and unchanged.

**Done.** The capability panel's state is `capabilities` when that read failed
and `entries` otherwise, so a failed `/v1/config/{node_id}/catalogue` shows the
panel's error state and names the dependency.

**Why.** The availability column is the reason the screen exists — "which of
these can run here, and what is blocking the rest". When the entries read
failed, every row rendered `—`, which is also exactly what a row renders when
nobody has an opinion about that capability. The panel said "we do not know" in
the words of "there is nothing to know", and a reader would have concluded the
deployment has no integrations rather than that a read failed.

It is one line, it is inside Scope B's own sentence ("a missing dependency takes
down a panel"), and a panel that takes the failure without showing it is not
taking it.

**Its proof needed a stub a total outage cannot build.** The first version of
this record cited the outage walk, which fails *both* reads at once and would
pass with the line reverted. `serveScenarioExcept` fails one dependency and
leaves the deployment healthy, which is the only way to say which of the two a
panel is reporting. Confirmed red with the line reverted to
`const catalogue = capabilities;`.

<!-- proof: console/tests/unit/surfaces/node-scope.test.tsx -->

---

## 4. Autonomy drops its breadcrumb crumb when no node resolves

**Planned.** Not mentioned.

**Done.** `nested={nodeId === '' ? [] : [{ label: nodeId }]}`.

**Why.** The header was `nested={[{ label: nodeId }]}` unconditionally. With no
node that renders a breadcrumb whose last step is blank, which reads as a page
that lost its subject rather than as a deployment that has none. `trailFor`
already draws no breadcrumb at all for a trail of one, so the empty list is the
shape that was already designed for this.

**Its proof is a pair, and it needed writing.** The first version of this record
cited the no-node render test, which only counts panels and would have passed
with the crumb left blank. There are now two named cases — the breadcrumb names
the node it resolved, and there is no breadcrumb element at all when it resolved
none — and the second is red with the conditional reverted.

<!-- proof: console/tests/unit/surfaces/node-scope.test.tsx -->

---

## 5. T-005 caught no third screen, and the walk it describes was already green

**Planned.** T-005: "a unit test that enumerates `AREAS` … and asserts a
rendered page with panel error states. Any screen that throws is fixed in this
task."

**Done.** `console/tests/unit/surfaces/outage.test.tsx`, two walks over `AREAS`.
No third screen was caught, so nothing was fixed under this task.

**Why it is two walks and not one.** The first — every read rejecting, viewer
resolved from the populated dataset — passed on its first run and would have
passed before this feature too, because the dataset's principal has a team node
and the two broken screens only broke without one. A test that was never red is
a regression guard whose value as a specification is unestablished, and saying
so is the honest option.

So there is a second walk: the same fourteen routes with the gateway
unreachable **and** a principal that resolves to no node. That is the state the
two broken routes were actually reachable in, and it is red without the fix —
confirmed by stashing `catalogue.tsx` and `autonomy.tsx`, running it, and
watching exactly the two failures the spec quotes from the server log:

```
× /autonomy: still renders — /v1/autonomy/policy/{node_id} needs a value for {node_id}
× /catalogue: still renders — /v1/config/{node_id}/catalogue needs a value for {node_id}
```

**What the walk adds that `screens.test.tsx` did not have.** That file serves a
503 to every read. A refusal and a silence are different exceptions — `ApiError`
and `TypeError` — and `panelRead` catches both but nothing was holding the
second. `serveOutage` rejects with the `TypeError` a real `fetch` produces when
a connection is never made.

The walk enumerates `AREAS` rather than the screen list, and its first assertion
is that the two agree, so a fifteenth area with no screen behind it fails here
rather than in a browser.

<!-- proof: console/tests/unit/surfaces/outage.test.tsx -->

---

## 6. `/v1/config` is read once more per page view on two screens

**Planned.** `plan.md` names this and accepts it: "one request per page view,
matching what configuration already pays".

**Done.** As planned, and worth stating plainly because it is the only cost this
feature adds. Catalogue reads it in parallel with `/v1/capabilities` and
`/v1/integrations`, so its wall-clock cost there is zero; autonomy reads it
first and serially, because it has nothing to do until it knows the node.

Both go through `panelRead`, so a config-service failure degrades the node
selection rather than the page — and `resolveNode` consults the viewer's team
before the tree, so on the common path a failed tree read changes nothing at
all.

**One case is knowingly left imprecise.** If the tree read fails *and* the
viewer resolves to no team, no node resolves, and the node-scoped panels show
their empty state rather than an error naming `/v1/config`. Strictly they are
saying "there is nothing here" when the truthful answer is "nobody could tell
us where to look". It is not fixed here for two reasons: it needs all three of
config-service down, a principal with no team, and no `?node=` in the address,
and the fix — threading the tree's failure into panels that never read it —
costs a branch on every node-scoped panel to improve wording in a case whose
page is already visibly degraded. Deviation 3's change is not the same shape:
there the panel *did* read the failing endpoint, and was rendering its result
as an absence.

---

## 7. Scope C's deploy wiring is not committed, because `.canary/` is not

**Planned.** T-007: "`.canary/deploy.sh`: after `guest smoke`, run
`tools/console_smoke.py` …".

**Done.** Exactly that, in `.canary/deploy.sh`, `.canary/config.env` and
`.canary/README.md`. None of the three is in the repository: `.canary/` is
excluded in `.git/info/exclude`, one developer's laboratory rather than
something the platform ships. The committed half of Scope C is
`tools/console_smoke.py`, its unit suite, and the contract assertion that holds
its path list level with the console's manifest.

**Why this is the right split anyway.** The walk is the part with a claim to
make, and it is testable without a container. The wiring is nine lines of shell
in a file that names one node and one container by number.

**What that means for a reader of the repository.** Anybody with their own
`.canary/` gets the walk by pointing `CONSOLE_SMOKE_URL` at a console; the
`--list` mode exists so a different deploy flow can consume the same list
without importing Python.

---

## 8. The plan's `README.md` "Evidence" deployment note does not exist

**Planned.** `plan.md` twice cites a README deployment note saying the console
is not served by any deploy path.

**Done.** No such note is in `README.md`; the only mention of the console there
is a line in the prior-art paragraph. `.canary/config.env` does carry a
`CANARY_CONSOLE_PORT`, but that is the *application* on a second port — the
guest script's own comment says "application and console are the same programme
on two ports", and there is no Node in the container and no console build in the
shipped bundle (`RUNTIME_PATHS` lists seven Python packages and four files).

**What was done about it.** The plan's conclusion survives its wrong citation:
the console genuinely is not served by the deploy, so the walk genuinely has to
be host-side and needs an address given to it. `.canary/config.env` now says
that in the place somebody configuring it will read.

---

## 9. The canary verification skipped migrations, and used a stand-in console

**Planned.** T-007: "verified by running `--canary-only` against the validation
container, recorded in deviations".

**Done.** Three runs against `pve02`, container 254:

1. `--canary-only --no-migrate`, `CONSOLE_SMOKE_URL` unset — the step printed
   `skipped: CONSOLE_SMOKE_URL is not set in .canary/config.env` and the run
   continued to its stop.
2. `--canary-only --no-migrate` against a stand-in console — fourteen routes,
   all 200, walk passed, nothing promoted.
3. A **full** `--no-migrate` deploy against a stand-in answering 500 on
   `/catalogue` and `/autonomy` — the run stopped with
   `fail: a console route did not answer 200 — the stable pair was never
   touched`, the canary was stopped, and `--status` afterwards showed the active
   release still `20260810-043859-139fad6`. Promotion was refused.

**Why `--no-migrate`.** The canary shares its database with the stable pair, and
the flow's own README says in as many words that a migration applied by a
release is not undone by a code rollback. Verifying a shell step is not worth an
irreversible write to somebody's laboratory database, and the step being
verified runs after migrations either way.

**Why a stand-in console rather than the real one.** What run 3 has to prove is
that `deploy.sh` reads the walk's exit code and stops before promoting. A real
console cannot be made to answer 500 on two routes on purpose — this feature is
the reason it no longer does — so the failing case needs something that can. The
passing case (run 2) was checked against the same stand-in for symmetry. The
walk itself is held against a real console's shapes by its own suite: the
sign-in form encoding, the session cookie, the redirect that is deliberately not
followed.

**What is therefore not proven by a run.** That the real console answers 200 on
all fourteen routes of a deployment with nothing configured. That is proven in
the gate instead, by T-001's five cases and T-005's twenty-eight, which render
the real screens against the committed dataset's empty scenario with a principal
that resolves to no node.

<!-- proof: tests/unit/tools/test_console_smoke.py::test_the_walk_visits_every_shell_route_signed_in -->
<!-- proof: tests/unit/tools/test_console_smoke.py::test_the_command_refuses_the_deploy_when_a_route_is_broken -->

---

## 10. `CONSOLE_SESSION_ENDPOINT` was added to the constants tier

**Planned.** Not mentioned.

**Done.** `config/constants/console.py` gained `CONSOLE_SESSION_ENDPOINT =
"/api/session"`, asserted equal to the console's own `SESSION_ENDPOINT` by
`tests/contract/console/test_console_shell.py`.

**Why.** The walk has to sign in the way a person does, and the address of the
console's sign-in handler is a fact both sides need. Every other name in that
group — the two cookies, the sign-in path, the lifetimes — is already declared
there and already held level by that test; a bare `"/api/session"` string in
`tools/` would have been the only one that drifts silently.

---

## 11. A URL with no credentials stops the deploy rather than skipping it

**Planned.** T-007 and `plan.md` describe one behaviour for the unset case:
"skip with a printed reason … never pass silently".

**Done.** `CONSOLE_SMOKE_URL` unset skips, out loud. `CONSOLE_SMOKE_URL` set
with either credential missing **stops the run** and names the variable.

**Why.** The console guards every route above the router, so an unauthenticated
walk gets fourteen redirects to the sign-in page. The walk does not follow
redirects, so it reports fourteen 307s and fails — but only because of that one
decision. Treating a half-configured walk as a skip would mean a deploy flow
that looks configured, prints nothing alarming, and checks nothing. Stopping is
the posture the plan asks for applied to the case it did not name: never pass
silently.

<!-- proof: tests/unit/tools/test_console_smoke.py::test_a_refused_sign_in_is_told_apart_from_a_broken_route -->

---

## 12. No browser-level outage variant, and why it cannot be one

**Planned.** `plan.md`: `console/tests/e2e/shell.spec.ts` "gains the 'gateway
down' variant only if it does not already have one (check during
implementation; the unit layer is the mandatory one)".

**Done.** Not added. The unit layer was built instead, which the plan names as
the required one.

**Why, concretely.** The shell renders on the *server*. Every read a screen
makes happens inside the Next process, not in the browser, so Playwright's
request interception — the mechanism a browser-level outage test would use —
cannot reach a single one of them. Producing the outage would mean stopping the
backing fixture server for the whole suite run, which breaks the other
fifty-nine tests sharing it, or standing up a second console process against a
dead backing just for this. Neither is worth it when the unit walk renders the
same fourteen screens through the same code with the same rejection.

What `shell.spec.ts` already does hold is the healthy half: it walks `AREAS` and
requires a rendered `page-header` with the right area on each, which is the
browser-level statement that no route 500s.

<!-- defer: theme=e2e-failure-mode-coverage -->

---

## 13. T-008 recaptured nothing, because nothing moved

**Planned.** T-008: "run the console gate; recapture affected baselines with
`make console-visual-accept` for the two screens only, and say so here".

**Done.** The visual suite ran and all twenty baselines passed, including
`autonomy-1440-light` and `configuration-1440-light`. No baseline was
recaptured.

**Why nothing moved.** The captures run against the populated dataset, whose
principal has a team node that is also the root of the tree. Both screens
resolve the same node they resolved before, read the same endpoints, and render
the same rows. The new behaviour only shows on a deployment that has no tree,
and no baseline photographs one.

**Catalogue has no baseline to move.** There is no catalogue entry in
`console/visual/screens.json` at all — the registry carries twenty captures and
none of them is that screen. So "recapture the two screens" was only ever one
screen's worth of work, and that one did not change. Adding a catalogue capture
is a gap in the visual registry rather than in this feature; it is not created
by anything done here, and photographing a screen for the first time is an
acceptance somebody reviews rather than a side effect of a bug fix.

<!-- defer: theme=visual-baseline-coverage -->

---

## 14. The gate, and one thing this file itself broke

**The console gate.** `python -m tools.console_gate all` exits 0: format-check,
lint, typecheck, lockfile, generated-client check, budget, the unit suite, the
browser suite at 60/60 and the visual suite at 20/20.

**The Python half.** `make verify` exits 0 end to end —
`12701 passed, 25 skipped` in 5m47s, including the console gate, the contract
suites, the architecture fixtures and the integration parity check.

**One thing about running it.** The two visual-regression contract tests
(`tests/contract/console/test_console_visual_regression.py`) fail if a second
console suite is running at the same time — they drive the same pinned browser
image and the same fixture port. Seen once here, from running the contract
suite and `console_gate all` concurrently; both pass alone and both pass under
`make verify`, which runs them in sequence. Not a flake in the ordinary sense
and not caused by this feature, but worth knowing before somebody parallelises
the gate.

**What broke, and was not the feature.** The first draft of *this file* named
the fictional deployment used by the committed dataset, and
`tests/architecture/test_one_fictional_deployment.py` failed on it: the guard
walks every `.md` in the repository and allows that name only under the mock
plane, the fixtures and `tests/`. Its `SKIPPED` set lists `specs` and `specs_v2`
as "local reference material that is never committed" — and `specs_v3`, which is
excluded exactly the same way, is missing from it.

**What was done.** The name was taken out of this file. Not the skip list: a
red gate caused by a note is a note to fix, and widening an architecture guard
to accommodate one is the shape of loosening a gate to pass it even when the
widening looks defensible. Recorded here because the next specs_v3 note that
quotes a fixture will hit the same wall, and the fix belongs to whoever owns
that guard rather than to a bug fix in the console.

---

## Appendix — where each item of the Definition of done is proven

| Item | Proof |
|---|---|
| 1 — `/catalogue` and `/autonomy` return 200 with nothing configured | `console/tests/unit/surfaces/node-scope.test.tsx` — `catalogue:`/`autonomy: renders rather than throwing when no node resolves`, against the dataset's `empty` scenario and a principal with no team node |
| 2 — all fourteen routes render with panel error states when every request fails | `console/tests/unit/surfaces/outage.test.tsx` — both walks, enumerated from `AREAS`, plus the assertion that `AREAS` and the screen list agree |
| 3 — the deploy walks fourteen routes signed in and refuses to promote on any non-200; unset prints why | `tests/unit/tools/test_console_smoke.py` for the walk and its exit codes; deviation 9 for the three runs against the container |
| 4 — a named "no node selected" test for every node-scoped screen | `console/tests/unit/surfaces/node-scope.test.tsx`, one case each for catalogue, autonomy and configuration |
| 5 — `make verify` green, including the console gate | Deviation 14 |

The path list held level with the console's manifest, in both directions:
`tests/contract/console/test_console_shell.py::test_the_deploy_walk_covers_exactly_the_areas_the_console_declares`.

<!-- proof: console/tests/unit/surfaces/node-scope.test.tsx -->
<!-- proof: console/tests/unit/surfaces/outage.test.tsx -->
<!-- proof: tests/unit/tools/test_console_smoke.py::test_the_walk_visits_every_shell_route_signed_in -->
<!-- proof: tests/contract/console/test_console_shell.py::test_the_deploy_walk_covers_exactly_the_areas_the_console_declares -->
