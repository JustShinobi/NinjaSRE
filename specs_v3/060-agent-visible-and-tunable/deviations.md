# Deviations — 060 The agent, visible and tunable

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards.

---

## 1. The pipeline had no declaration to serve, so one was written

**Planned.** T-001: "a read-only route serves the pipeline stage declaration
(names, order, what each consults) if none does today; otherwise pin the
existing shape."

**What existed.** `core/state/types.STAGE_ORDER` — six names in order — and
`core/pipeline/ownership.STAGE_WRITES`, the table the purity test enforces.
Neither says what a stage *consults*, and nothing outside the runtime could read
either without importing `core`, which the console may not do.

**Done.** `core/pipeline/declaration.py`: one `StageDeclaration` per stage, and
`GET /v1/agent/pipeline` over it.

**The half that is derived and the half that is not.** `writes` reads
`STAGE_WRITES` rather than repeating it — a second copy would agree on the day
it was written and drift into a screen describing a pipeline nobody runs.
`consults` and `summary` are written here, because there is no structure in the
repository that holds them: what a stage reads is expressed by which collaborator
it was constructed with, which is a fact about `build_pipeline`'s arguments
rather than a value anything can enumerate. Deriving them would have meant
inventing a registry to derive from.

**A stage that makes no model call names no role, and that is a decision.**
`plan_evidence` scores capabilities with deterministic arithmetic on purpose —
its own module says an LLM ranker would make two runs of one scenario
incomparable — and `resolve_integrations` and `deliver` reach no model either.
Giving those three a role for symmetry would put a model call on a screen where
there is none.

`<!-- proof: tests/unit/core/pipeline/test_stage_declaration.py::test_what_a_stage_writes_is_read_from_the_ownership_table -->`
`<!-- proof: tests/unit/core/pipeline/test_stage_declaration.py::test_a_stage_that_makes_no_model_call_names_no_role -->`
`<!-- proof: tests/unit/gateway/http/test_agent_routes.py::test_no_provider_and_no_model_identifier_leaves_this_route -->`

---

## 2. The outlook is an autonomy route, and its sentences are written in the future tense

**Planned.** T-002, and the plan: "the representative-action explain iteration,
which is a thin composition over the existing explain route", living "in the
gateway route layer over `platform/autonomy`".

**Done in two places rather than one.** `GET /v1/autonomy/policy/{node_id}/outlook`
— beside `explain` and `bounds`, sharing their `_service` and their tenancy
check — over `platform/autonomy/outlook.py`, which is where the composition
actually lives.

**Why not the gateway route layer alone.** Two things had to be true and only
one of them is HTTP's. The reading has to be of *one* posture: five calls to
`explain` resolve the configuration chain five times and can straddle a change
made between the first class and the last, producing a reading no policy set
ever held. And the sentences are testable without a server. `AutonomyService.outlook`
resolves once, decides five times through one gate, and the route renders it.

**Why the sentences are not `Decision.reason`.** The gate's own explanation is
written for something that happened — "ran without asking", "was refused". This
is a reading of a posture, about something that has not happened; rendering a
past-tense sentence beside a hypothetical is how a screen gets read as a log. So
`ClassOutlook.describe()` composes the future-tense sentence and the gate's own
reason travels beside it as the detail, naming the rule that decided.

`<!-- proof: tests/unit/platform/autonomy/test_outlook.py::test_each_sentence_names_the_class_and_says_what_would_happen -->`
`<!-- proof: tests/unit/gateway/http/test_autonomy_routes.py::test_the_outlook_follows_the_posture_that_is_actually_stored -->`
`<!-- proof: tests/unit/gateway/http/test_autonomy_routes.py::test_dry_run_is_reported_on_the_outlook_as_a_whole -->`

### The representative capability names are deliberately not real ones

`REPRESENTATIVE_ACTIONS` (`config/constants/autonomy.py`) names each entry "a
reversible restart of one workload" rather than `restart_workload`. Borrowing a
real capability's name would answer a narrower question while looking like it
had answered the broad one: a rule scoped to that capability would decide the
sentence, and every other capability in the class would be misreported. A test
asserts no entry collides with an installed tool, and another asserts every
declared resource kind is one the estate actually models — a kind nothing models
is a kind no `resource_kind` rule can be written against, so the reading would
silently ignore rules that exist.

`<!-- proof: tests/unit/platform/autonomy/test_outlook.py::test_no_representative_capability_borrows_a_real_tool_s_name -->`
`<!-- proof: tests/unit/platform/autonomy/test_outlook.py::test_every_representative_resource_kind_is_one_the_estate_models -->`

**What this reads on the committed dataset, and why it is dull.** All five
classes come back "would be proposed", because that dataset's deployment-wide
rule *is* `propose_only` and the two narrower rules — a capability scope and a
label selector — match no representative subject. That is the true answer for
that posture and it was left true rather than made interesting.

---

## 3. The capability join became a union, and the dataset it exposed was inconsistent

**Planned.** T-003: "extract the capability↔integration join the catalogue
screen computes into a shared console data function; failing test that both call
sites produce identical rows."

**Done.** `console/src/surfaces/capabilities.ts`, read by `/catalogue` and by the
agent screen's tools tab.

**One thing the extraction found.** The catalogue screen iterated
`/v1/capabilities` and looked each entry up in the node's catalogue, so an entry
the *node* resolved and the build's listing did not name never rendered at all.
On the committed dataset that was `metrics.range_query` — the only blocked
capability in it. The screen whose entire purpose is "which are blocked and
why" had never rendered a blocked row in a test. The join is now a union, the
node's answer leads, and the dataset's two files were reconciled so they describe
one deployment rather than two.

**The read/write split is a reading of the platform's scale, not a second one.**
`READ_ONLY_LEVELS` names two levels and everything else writes, including a level
this console has never heard of — the same default the platform takes for a
capability whose author declared nothing. A Python contract test holds the list
against `SIDE_EFFECT_LEVELS`, so a level added in Python fails in Python.

`<!-- proof: console/tests/unit/surfaces/agent.test.tsx -->`
`<!-- proof: tests/contract/console/test_console_surfaces.py::test_the_console_and_the_platform_agree_about_which_levels_only_read -->`

---

## 4. `/agent` takes `config.read`, not `investigation.read`

The manifest's rule is that an area carries "the permission the gateway requires
on the data the area reads", and the catalogue route's row states the tie-break:
where a screen reads two, it takes the narrower. This screen reads the node's
effective configuration, its field catalogue, its capability catalogue and its
posture — four `config.read` routes — beside one `investigation.read` route.

The consequence is worth stating because it is a real narrowing: somebody holding
only `investigation.read` cannot open this screen. The alternative was worse in
both directions — the area would appear for a viewer whose every panel then
failed, and the settings zone would stop being absent for a viewer who has
nothing in it.

---

## 5. `TabLinks`, a second tab component, on purpose

`Tabs` exists and is a client component that owns its selection. This screen's
section has to be in its address — `url-state.ts`'s rule, so a section can be
sent to a colleague — and the screen is a server component.

**Done.** `TabLinks` in `console/src/components/navigation.tsx`, registered in
the gallery like every other primitive. Two components rather than a prop,
because the keyboard contracts differ and both are right: `Tabs` has roving
focus and arrow keys because it owns the state; these are links, so every one is
in the tab order and the arrow keys are the browser's. Giving links roving focus
would borrow a pattern that only makes sense when the widget owns the selection.

---

## 6. The hierarchy extends `graph.tsx` rather than arriving as a second renderer

The plan's decision 2, followed. `HierarchyGraph` sits in the same module as
`DependencyGraph` and reuses its `Box`, its rounding, its stroke and its bound;
what changes is the axis. State is on the node *and* in the list beside it — a
disabled specialist is drawn faint and is marked in words, because a picture is
not the accessible copy of itself.

`<!-- proof: console/tests/unit/surfaces/agent.test.tsx -->`

---

## 6b. `ask` — the console gained a way to POST a question

T-009 asks for 058's recorded-action preview beside the representative set, and
the plan's decision 3 says both are shown when both are available. The route
that answers it is a `POST` — it takes a policy document and replays the
deployment's own decision history against it — and `src/lib/api.ts` could only
`GET`: `ReadablePath` is derived from the paths declaring a 200 under `get`.

**Done.** `ask` beside `read`, typed over `AskablePath`, which is the same
derivation under `post`.

**Why not one of the proxies under `src/app/api/`.** Those exist for exactly one
reason, which their own module docstrings state: a *browser* cannot present a
credential that lives in an HTTP-only cookie. A server component already holds
it, so a courier would be a hop that adds nothing and a second place to forget a
check. What keeps `ask` from being a write path is the caller rather than the
verb — every use of it is a question, and a route that changes something is
still reached through a proxy, where the closed operation table is.

The panel it exists for is absent for a reader who may not ask: the preview
route takes `config.write` because it reads the decision history to answer.

`<!-- proof: console/tests/unit/surfaces/agent.test.tsx -->`

---

## 7. What is not built, and is therefore still open

Recorded plainly rather than left to be discovered.

- **A bridged server's *tools* are not enumerated.** Acceptance 3 asks that
  MCP-origin tools be identifiable as such. What is built is the identification —
  a capability carrying the `bridged` tag renders with its server as origin, and
  the tools tab lists the outside servers this node registers, with their
  protocol, address and enabled state. What is missing is the data: nothing in
  the gateway holds a bridged catalogue. `capabilities/protocols/catalogue.py`
  builds one by *reaching each server*, and no composition root calls it —
  `bridged_catalogue` has no production call site anywhere. Enumerating them in a
  console read means a network call per request, a timeout policy and somewhere
  to cache the answer, which is a piece of work rather than a route.
  `<!-- handoff: to=061-proposed-changes what="compose a bridged catalogue at the gateway and serve it, so an MCP server's tools appear in the capability catalogue with their origin, their classification and their server's health" -->`

- **T-006's editing is a link, not a click-through, and there is no template.**
  The task asks for click-through to 058's catalogue-driven editor for the
  `agents` section, and a topology template applied through preview-then-save.
  058's editor deliberately edits scalars only and says so on the screen: a list
  replaces entirely on write, so a control over one would let a typo drop every
  entry but the one somebody retyped (058's deviations §1 and §12).
  `agents.subagents` is a list of objects. A click-through would land on a row
  that says it is not edited a field at a time, which is a worse answer than a
  link to the editor and a sentence saying which section to look in — which is
  what this screen does. The budgets and the model roles *are* scalars and do
  render with their ceilings and their provenance.
  `<!-- handoff: to=061-proposed-changes what="give the configuration editor a way to change a list of objects (agents.subagents is the first), then give the agent screen click-through per specialist and a topology template applied through preview-then-save" -->`

- **The e2e that T-006 asks for — disable a subagent, see provenance, re-enable —
  is not written**, because the console cannot disable one (above). What is
  written instead is T-010's, which is the acceptance the feature is judged on:
  the three questions answered from the rendered pages.

`<!-- proof: console/tests/e2e/agent.spec.ts -->`

---

## 8. The mock plane's effective configuration was flat, and now is not, for one section

058's deviations §6 record that the dataset's `config-effective` carries four
invented settings — `investigation.max_loops` and friends — as **flat dotted
keys**. The real route returns the merged settings *nested*, which is what
`ConfigService.resolve` produces. A screen reading `values.agents.subagents`
therefore found nothing in the dataset while working against a deployment.

**Done.** The `agents` section and `capabilities.protocol_servers` were added to
the populated `config-effective` record in the shape the route actually returns.
The four legacy flat keys were left alone: `tests/unit/tools/mockplane/test_server.py`
asserts against `investigation.n` by name, and rewriting them is 058's decision
to revisit rather than this feature's.

---

## 9. The visual baselines are recaptured, and twenty of twenty-three moved

Two reasons, both this feature's own and both structural. The navigation gained
an entry, and the navigation is in `Shell`, which wraps every route — so every
screen moved by the same handful of pixels. And the gallery gained `TabLinks`
(§5), which moves every gallery capture at every width and theme.

The three new ones are the agent screen's own sections. `visual/screens.json`
carries an acceptance record for each saying what it is for; the topology one is
worth reading, because what that baseline exists to catch is the single thing a
reviewer cannot see by reading the code — a vendor's model identifier appearing
beside a stage.

Recapturing rewrites committed PNGs and the acceptance is the commit somebody
reviews: `git diff console/visual/baselines/` is the review, and reverting that
path alone puts the old baselines back without touching any code.

---

## 10. Handoff d4639dd6 — closed, and it needed a route the table did not have

058 deferred "grant and revoke an autonomy override from the console; the proxy
already forwards POST /v1/autonomy/policy/{node}/overrides and the list already
shows duration and reason".

**Granting** was forwarded and uncalled, as the handoff says. **Revoking** did
not exist at all: there was no route, no service method and no row in the
permission table — an override could be granted from the console and then only
waited out.

**Done.** `AutonomyService.revoke_override` and
`DELETE /v1/autonomy/policy/{node_id}/overrides/{name}`, plus the console
controls for both.

**Two decisions inside it.** A revocation is written against the node's *own*
document, like the grant it reverses: revoking an inherited override would mean
copying every one of the parent's into this node in order to leave one out,
which is how a hierarchy stops being one. And an override this node did not
grant is a 404 whose message says so, rather than a quiet success — an operator
told a widening was removed stops looking, and the widening is still in force
from a level above.

`<!-- handoff-done: id=d4639dd6 -->`
`<!-- proof: tests/unit/gateway/http/test_autonomy_routes.py::test_an_override_is_granted_and_then_revoked_by_name -->`
`<!-- proof: tests/unit/gateway/http/test_autonomy_routes.py::test_revoking_an_override_this_node_never_granted_is_not_found -->`

---

## 11. Handoff f5c72804 — closed, and the last-owner rule was already written

058 deferred "serve POST/DELETE /identity/grants and give the administration
screen role add and remove, rendering the last-owner refusal as its own
message".

**Done.** Both routes in `gateway/http/routes/identity.py`, plus the console
controls.

**Three decisions inside it.**

- **A grant's identifier is derived, not random.** `grant:{principal}:{role}:{node}`,
  so granting the same role at the same node twice is one grant rather than two.
  Two identical bindings are one fact stored twice, and the second is only ever
  discovered by whoever tries to revoke the role and finds it still held.
- **The principal has to exist first.** Creating one here would turn a typo in an
  identifier into a new account holding a role.
- **The last-owner refusal came free and is the interesting half.**
  `require_owner_retained` already existed, already evaluated the rule over the
  whole organisation rather than per removal — so handing ownership over in one
  operation is allowed and removing the last owner is not — and had no call site
  outside its own test. It is a 409 with its own message, because "no" without a
  reason sends somebody looking for a permission they already hold.

Both routes leave an audit row through `PERMISSION_AUDIT_ACTION_GRANT` and
`_REVOKE`, two more constants that existed with no caller.

### The grant form needed a role catalogue, and nothing served one

A form offering a role has to know which roles exist. The platform's catalogue
was generated into `fixtures/contract/roles.json` for the *tests* to walk, and
the first attempt at this imported that file into the console — which builds on
a laptop and fails in the production bundle, because Turbopack will not resolve
a module outside the application's own root. The build was red on it.

The fix is the one `tools/console_roles` argues for in its own docstring: the
deployment is the authority, so the deployment answers. `GET /identity/roles`
returns each role and the permissions holding it grants — the second half
because "what does granting this actually do" is the question somebody asks
*before* granting it, and answering it anywhere else would mean the console
deriving it.

`<!-- proof: console/tests/unit/surfaces/grants.test.tsx -->`

`<!-- handoff-done: id=f5c72804 -->`
`<!-- proof: tests/unit/gateway/http/test_identity_grant_routes.py::test_removing_the_last_owner_is_refused_with_its_own_message -->`
`<!-- proof: tests/unit/gateway/http/test_identity_grant_routes.py::test_ownership_can_be_handed_over_by_granting_first -->`
`<!-- proof: tests/unit/gateway/http/test_identity_grant_routes.py::test_a_grant_and_a_revocation_each_leave_an_audit_row -->`

---

## 12. Handoff fecce839 — closed

058 deferred "detector enable/disable with the dry-run offered in the enable
flow, and schedule CRUD with the destructive-action treatment; every gateway
route for both already exists". The gateway half was indeed complete; what was
missing was the console surface and its proxy, and — for schedules — anything in
the mock data plane to render, since `GET /v1/schedules` was served by the
deployment and unknown to the dataset.

**Done.** The schedule listing is now an endpoint the mock plane knows, with two
records in the populated scenario (one enabled, one not) so both states are
photographed. The detector controls and the schedule surface sit on the
detectors screen: a recurring investigation is what is being watched for on a
clock, and giving it an area of its own would have added a navigation entry for
two rows.

The permission the brief carried was wrong and the deployment's was right: the
detector writes take `incident.manage` and every schedule route takes
`schedule.manage`, which is what the route table declares and therefore what the
screen gates on. The schedules panel is absent rather than read-only for a
viewer without it, because the listing route requires the same permission — a
read-only view of it does not exist to offer.

`<!-- proof: console/tests/unit/surfaces/detector-controls.test.tsx -->`
`<!-- proof: console/tests/unit/surfaces/schedules.test.tsx -->`

`<!-- handoff-done: id=fecce839 -->`

---

## 13. A shared module was renamed so a guard did not have to be weakened

`make check-console-boundary` reads a console file's relative imports and
compares the first segment against the Python package names. The join extracted
in §3 was called `capabilities.ts`, so `../capabilities` — a sibling module,
well inside `console/src/` — read to the guard exactly like a console file
reaching into `capabilities/`.

Teaching the guard to resolve the path first would have been defensible and is
still the wrong move here: a check script edited so that new code passes it is
indistinguishable, six months later, from a check script that was weakened. The
module is `capability-rows.ts`, its own docstring says why, and the guard is
untouched.

---

## 14. One test file collided with another by basename, and `make verify` said so

`tests/unit/core/pipeline/test_declaration.py` and
`tests/unit/core/capability/test_declaration.py` cannot both be collected: the
test tree has no `__init__.py`, so pytest imports by basename and the second one
it reaches is an import mismatch rather than a test. It passes when run alone,
which is how it survived until the whole suite ran.

Renamed to `test_stage_declaration.py`, which is also the better name — what it
describes is the stage declaration rather than declarations in general.
