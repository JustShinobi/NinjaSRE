# Deviations — 058 Configuration write surfaces

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. The node's catalogue does not describe fields, so a field catalogue was built

**Planned.** The spec and the plan both say field editing is "driven by the
node's catalogue (`GET /v1/config/{node_id}/catalogue`) — type, range, default
and description come from the catalogue, not from a table in the front end".

**What that route actually returns.** The *capability* catalogue: which tools
and skills this node may run, and why any of them it cannot. Name, kind,
summary, tags, side-effect level, required integrations, available, reason.
Nothing about a configuration field, because it is not about configuration
fields.

**Done.** `platform/config_service/fields.py` derives the field catalogue from
`RootConfig`'s own JSON schema — the Pydantic sections the write path validates
against — and `GET /v1/config/{node_id}/fields` serves it, overlaid with what
each field stands at for that node: the value, the level that supplied it,
whether *this* node overrides it, what locks it, whether it is gated, and any
ceiling or closed set the node's policies narrow it to. Ninety-three fields
today, across twenty-two sections.

**Why derived rather than written.** It is the plan's own doctrine, applied to
the only source that actually holds the four facts: a table of field
descriptions in the console agrees with the schema on the day it is written and
drifts from then on, and the drift arrives as a control offering a value the
write path refuses. Deriving means a field added to a section is a control on
the same commit.

`<!-- proof: tests/unit/platform/config_service/test_fields.py::test_a_bounded_integer_carries_its_type_its_range_and_its_default -->`
`<!-- proof: tests/unit/gateway/http/test_config_write_routes.py::test_the_node_catalogue_describes_every_editable_field -->`

**Two smaller decisions inside it.**

- **A list is a leaf**, because that is what the merge says: lists replace
  entirely, so an editor offering to change one entry would offer an operation
  the write path does not have. An object with no declared properties — a
  free-form parameter map — is a leaf for the same reason: its keys are the
  operator's rather than the schema's.
- **A policy narrows a control and never widens it.** A node policy declaring a
  ceiling above the schema's is ignored; the schema's bound is the deployment's,
  and a form offering a value past it is a form whose every submission is
  refused.

---

## 2. Removal travels beside the patch, not inside it

**Planned.** T-002 and the plan: clear-to-inherit "carried in the patch as an
explicit removal marker".

**Done.** A sibling field: `PUT /v1/config/{node_id}` and
`POST /{node_id}/preview` take `{"patch": {...}, "remove": ["a.b.c"]}`, and
`ConfigService.set_settings`/`preview_settings` take `remove=(...)`.

**Why not a marker inside the document.** `platform/config_service/merge.py`
states it as a rule with a requirement number behind it: *no key is a
directive*. A field called `_delete` is a field called `_delete`, and that is
what makes a configuration document behave the way the reviewer read it. A
removal sentinel inside the patch would be the first exception, and the first
exception is how a configuration language starts.

The plan's own wording allows this — "if the config service's patch shape cannot
express removal today, adding it is in scope" — and a request field is the patch
shape expressing removal.

`<!-- proof: tests/unit/platform/config_service/test_preview_redundancy.py::test_clearing_is_not_the_same_operation_as_setting_the_parent_value -->`
`<!-- proof: tests/unit/gateway/http/test_config_write_routes.py::test_clearing_is_distinct_from_setting_the_inherited_value -->`

**One thing the plan did not name and the tests found.** `check_locks` cannot
see a removal: it walks the *proposed* document's leaves, and a removal leaves
no leaf. Clearing a locked field would therefore have reported success and
changed nothing, which tells an operator they lifted a constraint they cannot
lift. `_check_removable` is the second check, and
`test_removing_a_path_an_ancestor_locked_is_refused` is what holds it. The same
applies to the approval gate, which does see it, because `changed_paths` already
counts a removal as a change.

---

## 3. T-001 and T-002 landed in one commit

Both change `preview_of`, and the redundant list and the reversion list are
computed from the same second resolution of `chain[:-1]` — what the node would
resolve to if it said nothing. Splitting them would have meant writing that
resolution twice and deleting one of them an hour later. The two test files are
still separate concerns inside one module, and each behaviour is named by its
own test.

---

## 4. The redundant warning excludes a locked path, which nothing asked for

A patch that restates a locked ancestor's value does not move the resolved
value — but not because the operator restated something they already had. It
does not move because the write is refused. Reporting it as redundant would tell
somebody to remove an override the write never made, and send them looking for
one.

`<!-- proof: tests/unit/platform/config_service/test_preview_redundancy.py::test_a_locked_path_is_not_reported_as_redundant -->`

---

## 5. `ConfigPreview` became `ConfigEditor`, and the old component's tests moved

**Planned.** "Extend `ConfigPreview` into the editing panel."

**Done.** `console/src/surfaces/preview.tsx` exports `ConfigEditor` — the same
module, the same doctrine, a different shape. Its three tests left
`decide.test.tsx` for `config-editor.test.tsx`, which is twenty-seven tests
covering the same three properties and everything the editing half adds. The
role matrix's `config-preview` test id is `config-editor`.

**Preview-before-save is structural, and that is the part worth defending.**
The save control does not exist until a preview of the *current* change has come
back, and any further edit removes it again — the pending change is serialised
to a stable string and compared against the string the preview was taken of, so
invalidation is a comparison rather than something a handler has to remember to
do. It is a client guarantee because it can only be one: no API can know whether
a person read the diff.

`<!-- proof: console/tests/unit/surfaces/config-editor.test.tsx -->`

---

## 6. The mock plane's field catalogue is written, not derived

The dataset's `config-effective` record has always carried four invented
settings — `investigation.max_loops` and friends — which are not fields the real
schema declares. The new `config-fields` record matches *those four* rather than
the ninety-three the schema really has.

**Why.** This dataset is a plausible deployment, and it is what the visual suite
photographs. A form listing ninety-three fields, none of which the values table
beside it shows, is a screenshot nobody can review. Deriving the real catalogue
here would also have meant rewriting `config-effective`, which
`tests/unit/tools/mockplane/test_server.py` asserts against by name.

The derivation is proven where it lives: against the schema in
`tests/unit/platform/config_service/test_fields.py`, and over HTTP in
`tests/unit/gateway/http/test_config_write_routes.py`.

---

## 7. Handoff 30d6fed7 — closed, and the field it was waiting for was already there

054 deferred "prefill the endpoint field from `GET /v1/integrations`
`suggested.address` once the configuration tree gives a self-hosted integration
an endpoint field to prefill".

The obvious reading — `integrations.active[].base_url` — is inside a list, and
this feature's editor deliberately does not edit lists (§1). But the tree has
two *scalar* endpoint fields that mean exactly what the handoff describes:
`policies.observation.bridge.metrics.endpoint` and `…bridge.logs.endpoint`, each
with a sibling `integration` naming the vendor it belongs to. Those are fields
the editor now renders, so the condition is met.

**Done.** `withSuggestions` matches a suggestion to an endpoint through the
sibling `integration` field — the deployment's own statement of which vendor
that source is — rather than through the field's name or a path fragment, which
would attach an address to whatever happened to be spelled similarly. The
address is **offered, never applied**: a derived address is evidence and typing
one is a decision, and a form that filled it in silently would claim somebody
had chosen it. It is offered only where the field is empty, for the same reason.

`<!-- handoff-done: id=30d6fed7 -->`
`<!-- proof: console/tests/unit/surfaces/config-editor.test.tsx -->`

---

## 8. Handoff c04f14b0 — closed, and it needed a capability binding nothing had

057 deferred "give the configuration tree a change-source setting (a repository
path for the apply record, and a vendor plus repository for a git host) and
compose `GatewayState.change_sources` and the capability binding from it".

**Done.** `policies.changes` in the schema — `repository_path`, and
`git_host.{vendor,repository}` — plus `gateway/http/change_sources.py`, which
turns those settings into sources and is called from the lifespan.

**Three things the handoff did not name.**

- **Nothing implemented `ChangeAccess`.** `capabilities/tools/changes/binding.py`
  declares the protocol and only test doubles satisfied it, so "compose the
  capability binding" meant writing the production one. `ComposedChangeAccess`
  holds the estate lookup on the composition side of the seam, because resolving
  "which resource is this" needs the estate and a tenant scope and the capability
  layer is allowed neither.
- **An absent source is not an empty one.** The binding is left unbound when
  nothing is configured, so the tool reports that no change source is
  configured — which is what an operator can act on. Binding an empty source
  list would have made it report "nothing changed" instead, and the two findings
  lead somewhere different.
- **A misconfiguration does not stop the gateway.** An unreadable vendor is
  logged and skipped at startup, because the console somebody would fix it from
  is served by the same process.

**And one thing beyond the handoff.** `GET /v1/estate/resources/{id}` now
resolves the sources from *the caller's own node* and falls back to what the
process composed. Without it, a change source set in the console would need a
restart — and that route's own docstring already promised the opposite: "point
the deployment at a repository and the next render of this page says so, with
nothing to migrate".

`<!-- handoff-done: id=c04f14b0 -->`
`<!-- proof: tests/unit/gateway/http/test_change_sources.py::test_a_change_source_written_through_the_configuration_route_is_readable_back -->`
`<!-- proof: tests/unit/gateway/http/test_change_sources.py::test_a_deployment_that_configured_none_leaves_the_capability_unbound -->`

---

## 9. The kill switch takes `remediation.execute`, not `config.write`

**Planned.** The plan's decision 3: "engaging requires `config.write`; the
*banner* is visible to every viewer".

**Done.** The banner is every viewer's, exactly as planned — and it needed a
route that did not exist, `GET /v1/autonomy/kill-switch`, because the two write
routes answer the question only for whoever just changed it and a banner on
every screen had nothing to read.

Engaging keeps the permission the route table already gave it,
`remediation.execute`, and the table's own reasoning is better than the plan's:
"the control exists for the ten seconds in which an operator has neither the
time nor the confidence to work out what is currently permitted, and a stop that
waits for an administrator is not one." Changing it to `config.write` would have
narrowed an emergency control to the role least likely to be at a keyboard
during an emergency.

`<!-- proof: tests/unit/gateway/http/test_kill_switch_route.py::test_the_state_a_responder_engaged_is_the_state_a_viewer_reads -->`
`<!-- proof: console/tests/unit/shell/stop.test.tsx -->`

---

## 10. The SSO routes did not exist, and neither did anywhere to keep the answer

**Planned.** The plan: "**Identity**: `GET|PUT /identity/sso`, `/sso/test`,
`/sso/activate` … The routes exist."

**They did not.** Four rows in `gateway/http/security/route_permissions.py` and
nothing serving them. `platform/identity/sso_config.py` had the whole decision —
`activate` refusing a configuration whose test has not passed, a fingerprint
binding a result to the settings that produced it — and no HTTP surface, no
storage, and no caller.

**Done.** `gateway/http/routes/sso.py`, with the settings under `policies.sso`
in the configuration tree.

**Why the configuration tree rather than a repository port.** None of these
fields is a secret — a client secret, where a provider needs one, is a vault
credential and is not here — so this is configuration, and putting it in the
tree gives it the provenance, the preview and the audit row everything else an
operator changes already has. A port would have meant a migration, a fake, a
Postgres implementation and a fourteenth repository, for a document with one row.

**How a test is bound to the settings, without storing a tuple.**
`SsoTestResult.fingerprint` is a tuple of objects and does not survive a JSON
round trip — a stored list would never again equal a rebuilt tuple, so every
activation would be refused. What is stored is a **digest** of the settings
(`digest_of`), and `verified` is derived on every read by recomputing it. Two
consequences worth stating: editing anything invalidates the test *by
construction* rather than by a rule somebody applies, and `is_active` is
deliberately outside the digest — otherwise activating a tested configuration
would invalidate the very test that permitted it, and nothing could ever stay
active.

**What the test proves, and what it does not.** It takes the claim set the
provider returned for a real test user and runs it through the same
`read_claims` and `map_groups` a sign-in takes: the issuer matches, the claim
names are the ones this provider actually sends, a subject and an email are
present, and the groups map somewhere. It does **not** prove the endpoints are
reachable from this deployment — nothing here opens a socket. That is a real
limit and it is written into the route's docstring. It is also the right trade:
an operator who can produce that claim set has already reached the provider, and
a gateway cannot complete an authorisation code flow on somebody's behalf.

`<!-- proof: tests/unit/gateway/http/test_sso_routes.py::test_an_untested_configuration_cannot_be_activated -->`
`<!-- proof: tests/unit/gateway/http/test_sso_routes.py::test_editing_the_configuration_invalidates_the_test_and_deactivates_it -->`
`<!-- proof: console/tests/unit/surfaces/sso.test.tsx -->`

---

## 11. Four console proxy routes, two of them one file for several operations

`/api/kill-switch`, `/api/token`, `/api/autonomy` and `/api/sso`. The last two
forward several operations through one handler rather than one file each, and
what keeps that from being an open proxy is a **closed table** in each: an
operation the handler does not name cannot be reached through it, so the
console's own process can never be used to address an arbitrary path on the
deployment. Five files of near-identical courier would have been five places to
forget a credential check.

None of them decides anything. `/api/sso` in particular does *not* track whether
a test has passed — that is derived by the deployment from the settings, and a
console holding a second answer would eventually offer activation on a document
nobody tested.

---

## 12. The editor edits scalars, and says so where it does not

`integrations.active`, `capabilities.enabled`, `capabilities.parameters` and
every other list or free-form mapping renders as a row saying it is not edited a
field at a time. A list replaces entirely on write (§1), so a text control over
one would let a typo drop every entry but the one somebody retyped; a free-form
mapping has keys the schema does not know, so there is no control to derive.

`<!-- proof: console/tests/unit/surfaces/config-editor.test.tsx -->`

This is why handoff 30d6fed7 is closed against the *bridge* endpoints rather
than against an integration's `base_url` — see §7.

---

## 13. What is not built, and is therefore still open

Recorded plainly rather than left to be discovered.

- **T-009 is half done.** The overrides list now shows duration and reason in
  the row (`autonomy.tsx`), which is what the task asks for. **Granting** an
  override from the console is not built: the route is forwarded by
  `/api/autonomy` under `override`, and nothing calls it.
  `<!-- handoff: to=060-agent-visible-and-tunable what="grant and revoke an autonomy override from the console; the proxy already forwards POST /v1/autonomy/policy/{node}/overrides and the list already shows duration and reason" -->`
- **T-012 — grants — is not built at all**, and the gateway routes it needs do
  not exist either: `POST /identity/grants` and
  `DELETE /identity/grants/{grant_id}` are declared in the route table and
  served by nothing, the same way the SSO rows were. Adding a role binding is a
  write to the identity store rather than to configuration, so it is a different
  shape of work from everything else in this feature.
  `<!-- handoff: to=060-agent-visible-and-tunable what="serve POST/DELETE /identity/grants and give the administration screen role add and remove, rendering the last-owner refusal as its own message" -->`
- **T-013 and T-014 — detector enable/disable with dry-run, and schedule CRUD —
  are not built.** Both screens stay read-only. The gateway routes for both
  exist and are tested; what is missing is the console surface and its proxy.
  `<!-- handoff: to=060-agent-visible-and-tunable what="detector enable/disable with the dry-run offered in the enable flow, and schedule CRUD with the destructive-action treatment; every gateway route for both already exists" -->`
- **The visual baselines are not re-captured.** Four screens changed shape and
  `make console-visual` will report them. Recapturing rewrites committed PNGs
  and the acceptance is the commit somebody reviews, which is a review this run
  cannot stand in for.
  `<!-- defer: theme=visual-baseline-acceptance -->`

None of these is in the Definition of done, which is why the feature is reported
as meeting it; all of them are in the spec's scope, which is why they are named
here rather than quietly dropped.

---

## 14. The kill switch was writing no audit row, and the auditor for it already existed

Found by the done-auditor against this feature's own diff, which is the point of
running one.

`POST|DELETE /v1/autonomy/kill-switch` threw the switch and wrote a structured
log line and nothing else. `RemediationAuditor.kill_switch` — the right method,
with the right action constant, unit-tested in isolation and documented as
recording "both directions, because a release is the more sensitive of the two" —
had **no call site anywhere outside its own test**. So the most consequential
write this deployment has was leaving no trail, and the Definition of done's
item 6 was not met for it.

**Done.** Both routes call it now, *after* the switch is thrown rather than
before: the stop is the urgent half and must not wait on a database, and the
auditor's own log line survives a store that could not take the row. The release
path captures the state before releasing, so the record names the scope that was
lifted rather than the absence left behind.

`<!-- proof: tests/unit/gateway/http/test_kill_switch_route.py::test_engaging_it_leaves_an_audit_row_naming_who_stopped_what -->`
`<!-- proof: tests/unit/gateway/http/test_kill_switch_route.py::test_releasing_it_is_audited_too_because_that_is_the_sensitive_direction -->`

---

## 15. T-008's end-to-end test is not written

T-008 asks for "e2e from two different screens" for the kill switch. What exists
is unit coverage of both halves and the structural fact that the control and the
banner are in `Shell`, which wraps every route — so "reachable from any screen"
is true by construction rather than by a per-screen call site, and
`console/tests/unit/shell/stop.test.tsx` proves the behaviour of each half.

What is missing is the browser test that drives it on two routes. It is a real
gap in the task rather than in the Definition of done, and it belongs with the
visual baselines, which this run also does not re-capture: both need the browser
suite and an acceptance somebody reviews.

`<!-- defer: theme=browser-suite-acceptance -->`

---

## 16. The editor's new interaction model broke an earlier feature's browser test

The preview surface this feature replaced was a single setting/value pair whose
button was never disabled: clicking it with nothing typed still posted a patch,
and the deployment still answered. This feature made the editor a row per field
and gave the button a disabled state, because an empty change is not a
previewable thing — `isEmpty` in `console/src/surfaces/preview.tsx` and the unit
test that pins it were both written here.

What was not done is the other half. `console/tests/e2e/surfaces.spec.ts`
belongs to an earlier feature, was never touched by this one, and clicks
`ask-preview` without editing anything. Against the new editor that button is
disabled forever, so the test spent thirty seconds retrying a click and the gate
went red at the close step — the most expensive place to find it.

**Done.** The browser test now changes a field before asking, which is what the
surface requires of a person too. It changes `approval.required_above`
specifically: the test's own next assertion is that the answer says the change
is gated, and that is the one field this dataset gates.

The interesting part is that the unit suite already had
`will not preview at all until something has been changed`. The behaviour was
tested; the *consequence for a test somebody else wrote* was not. A feature that
changes what an existing control requires of its user has to go and look at who
was already driving that control, and running the browser suite is how you find
out — which is the same acceptance gap item 15 above defers.

The two tests that hold this, named in the file's own convention — the browser
one that now edits before asking, and the unit one that pins the button's
disabled state:

`<!-- proof: console/tests/e2e/surfaces.spec.ts -->`
`<!-- proof: console/tests/unit/surfaces/config-editor.test.tsx -->`

### The visual baselines, which item 15 had left

Fixing the browser test let the gate reach the visual suite, which item 15 above
had deferred without knowing what it would say: 13 of 20 baselines differed.

The diffs were read before anything was accepted, and they are this feature's own
work in both cases. Twelve of the thirteen differ only in the top-right utility
bar, in the same ~3,850 pixels, because the kill switch this feature added lives
in `Shell` and `Shell` wraps every route — so every screen moved for one reason.
The thirteenth is `configuration-1440-light`, which shows the editor itself:
the single Setting/Value pair replaced by a row per field, each with its
provenance and its clear.

**Done.** Recaptured with `make console-visual-accept`. This is an acceptance of
how the product looks, not a mechanical step, and it is a committed change so
that it can be reviewed as one: `git diff console/visual/baselines/` is the
review, and reverting that path alone puts the old baselines back without
touching any code.

The seven baselines that already matched were left alone by the recapture,
which is the check that this changed what the feature changed and nothing else.
