# Deviations — 055 Closing the loop

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each acceptance criterion is proven

| Criterion | Where it is proven |
|---|---|
| 1 — a fired alert reaches the deployment and creates an investigation in under a minute | **Not proven against the live cluster.** See §9. The path is proven end to end offline by `tests/unit/gateway/webhooks/test_delivery_permission.py::test_a_token_scoped_to_it_delivers_an_alert` and `tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_investigation_starts_knowing_which_resource_it_is_about` |
| 2 — the alert resolves to the right resource; an unknown target is a stored, visible finding | `tests/unit/platform/estate/test_alert_resolution.py` (all ten), `tests/unit/gateway/webhooks/test_alert_ingress.py::test_a_resolved_alert_makes_the_incident_point_at_the_resource`, `::test_an_unknown_target_is_stored_on_the_incident_rather_than_dropped`, `::test_an_unknown_target_is_readable_over_the_api`, `console/tests/unit/surfaces/unresolved-targets.test.tsx` |
| 3 — firing then resolved of one group is one investigation | `tests/unit/gateway/webhooks/test_alert_grouping.py::test_a_firing_then_a_resolution_of_one_group_is_one_investigation` and `::test_the_resolution_closes_the_incident_the_firing_opened` |
| 4 — the investigation cites ≥3 distinct sources, attributed per claim | `tests/synthetic/test_first_investigation.py::test_the_conclusion_draws_on_at_least_three_distinct_sources`, `::test_every_validated_claim_names_the_evidence_behind_it`, `::test_the_claims_between_them_reach_every_source_the_run_used` |
| 5 — with dry-run on, remediation exists only as a recorded proposal | `tests/synthetic/test_first_investigation.py::test_the_run_executed_nothing_with_a_side_effect` and `::test_with_dry_run_on_the_proposal_is_recorded_and_nothing_runs` |
| 6 — the investigation replays | `tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_run_the_alert_started_replays_from_its_own_recorded_events` (the route the specification names), and `tests/synthetic/test_first_investigation.py::test_the_whole_investigation_replays_from_its_recorded_events` (the pipeline's own event stream). See §16 |

<!-- proof: tests/unit/platform/estate/test_alert_resolution.py::test_an_instance_label_resolves_to_the_resource_holding_that_address -->
<!-- proof: tests/unit/gateway/webhooks/test_alert_ingress.py::test_a_resolved_alert_makes_the_incident_point_at_the_resource -->
<!-- proof: tests/unit/gateway/webhooks/test_alert_ingress.py::test_an_unknown_target_is_readable_over_the_api -->
<!-- proof: tests/unit/gateway/webhooks/test_alert_grouping.py::test_a_firing_then_a_resolution_of_one_group_is_one_investigation -->
<!-- proof: tests/synthetic/test_first_investigation.py::test_the_conclusion_draws_on_at_least_three_distinct_sources -->
<!-- proof: tests/synthetic/test_first_investigation.py::test_with_dry_run_on_the_proposal_is_recorded_and_nothing_runs -->
<!-- proof: tests/synthetic/test_first_investigation.py::test_the_whole_investigation_replays_from_its_recorded_events -->
<!-- proof: tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_run_the_alert_started_replays_from_its_own_recorded_events -->

---

## 1. The fingerprint does **not** prefer `groupKey`, and the reason is a field with two jobs

**Planned.** `plan.md` §C and T-004: "the fingerprint prefers the group key +
resolved resource when present and falls back to the current composition".

**Done.** The alert carries `group_key`, it is recorded on the incident, and the
fingerprint is `team | source | alert name | components | resolved resource`.
The group key is **not** in it.

**Why, and it is not a preference.** `groupKey` is already load-bearing in this
build as the *delivery* identifier: `gateway/webhooks/sources/alertmanager.py`
declares `event_id_of = field(payload, "groupKey")`, which is what
`webhook_idempotency` deduplicates repeated HTTP deliveries by. Two shipped
tests pin that reading in as many words —
`tests/unit/gateway/webhooks/test_router.py::test_a_duplicate_alert_within_the_window_is_linked_not_discarded`
varies `groupKey` to make "a different delivery of the same underlying alert",
and `::test_a_resolution_is_linked_to_its_investigation` comments that "a fresh
`groupKey` here is what tells it apart from the firing delivery for
idempotency".

Making the same field the *group identity* inverts both. Under the planned
change the first test's second delivery becomes a different group and starts a
second investigation, and the second test's resolution stops finding the
incident its firing opened — which is acceptance 3 failing. Neither is fixable
without editing a shipped test to mean the opposite of what it says, and the
instruction is explicit that a red gate means the feature is wrong rather than
the gate.

**What the plan actually wanted, and where it landed.** The purpose of the
change was that a storm of one group is one investigation and that two machines
under one rule are two. The first is existing behaviour (identical alert name
and components), asserted now against the real payload shapes in
`test_alert_grouping.py::test_a_storm_of_notifications_of_one_group_is_one_investigation`.
The second is genuinely new and comes from the *other* half of the planned key —
the resolved resource — which is in the fingerprint:
`::test_the_same_rule_on_a_second_guest_is_a_second_investigation` is red
without it, because two containers firing `ContainerMemoryHigh` carry the same
name and no distinguishing component.

**What is left undone, and it is worth saying plainly.** Because `groupKey` is
the delivery id, a real Alertmanager re-notification of an unchanged group is
answered as a duplicate delivery rather than linked to the open investigation.
That is a defect in the idempotency key rather than in the fingerprint, it
predates this feature, and fixing it means deriving a delivery identifier
Alertmanager does not send (group key + status + `startsAt`). Handed on rather
than done here, because it changes what "a duplicate delivery" means for every
source and belongs with the ingress observability screen that would show it.

<!-- handoff: to=062-data-ingress-and-delivery what="derive an Alertmanager delivery identifier instead of using groupKey, so a re-notification of an unchanged group links to the open investigation rather than answering as a duplicate delivery" -->

<!-- proof: tests/unit/gateway/webhooks/test_alert_grouping.py::test_the_same_rule_on_a_second_guest_is_a_second_investigation -->
<!-- proof: tests/unit/gateway/webhooks/test_alert_grouping.py::test_a_storm_of_notifications_of_one_group_is_one_investigation -->

---

## 2. A resolved alert's incident has **one** subject, and it is the resource

**Not in the plan.** `plan.md` §B says the resolution "descends into the
investigation's initial context" and "into the incident record"; it does not say
what happens to the subjects `raise_for_alert` was already building from the
alert's components.

**Done.** When the alert resolved, the incident carries exactly one subject —
the estate resource — with evidence naming how it matched (`matched_on`,
`target_label`, `target`, `zone`, `group`). The component names are not repeated
as subjects.

**Why.** `IncidentSubject.resource_id` is rendered by `/incidents` as a list of
one kind of thing, and putting `adguard` (a label value) beside
`proxmox:container/hal9000/110` (a resource identifier) in that list makes the
list mean two things. The components are not lost: they are in the normalised
alert, in the objective the run starts with, and in the alert record. What the
subject buys by being the resource is that `/resources` shows the incident, via
the `ResourceReference` the handler now writes.

**Unresolved is the converse and deliberately additive.** The finding leads the
subject list and the component subjects follow it, because the list is bounded
by `MAX_INCIDENT_SUBJECTS` and an alert naming that many components would
otherwise push the finding off the end — which is the exact behaviour the
finding exists to replace.

**One behaviour change worth naming.** `_subjects` now truncates to
`MAX_INCIDENT_SUBJECTS` where the previous code let `Incident.__post_init__`
raise `BoundExceeded`. Adding a subject to a full list would otherwise have
turned a busy alert into a 500 on the ingress path.

<!-- proof: tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_resource_records_the_incident_that_named_it -->

---

## 3. Zone comes from the estate's own neighbours, not from a declared map

**Planned.** `spec.md` §B: "`instance` / `host` → address → zone by the `/24` →
resource".

**Done.** `resolve_alert` matches the address **exactly** against the `address`
attribute 053 writes onto a resource, and uses the zone only to make the
*finding* useful. `ZoneMap` is an optional argument; with none, an unmatched
address is placed by the zone its `/24` neighbours in the estate report, and
only when they agree on one.

**Why the exact match rather than the zone step.** The zone is a narrowing, and
the estate already holds the thing it would narrow to: 053 writes both `address`
and `zone` onto every guest. Going address → zone → resource would be a coarser
lookup with an extra way to be wrong.

**Why the zone at all, then.** The finding. "An alert arrived for 10.20.20.99"
is a fact; "…which sits in the apps zone, and no resource there holds that
address" is something an operator acts on. And the webhook handler has no
declared `ZoneMap` — that lives in an enrichment plan, applied at sweep time and
not kept — so inferring from the neighbours is what makes the sentence available
at all. A declared map, when a caller has one, outranks the inference, because
an operator's networks are a decision and a neighbourhood is a guess.

<!-- proof: tests/unit/platform/estate/test_alert_resolution.py::test_an_unmatched_address_carries_the_zone_its_neighbours_sit_in -->
<!-- proof: tests/unit/platform/estate/test_alert_resolution.py::test_a_declared_zone_map_outranks_what_the_neighbours_imply -->

---

## 4. Blackbox targets resolve through the `domain` attribute, not the topology edge

**Planned.** `plan.md` §B: "blackbox `target` → domain → workload via the
service→workload topology edge 053 built from `services.yaml`".

**Done.** Through the `domain` attribute on the workload, which is what 053's
enrichment writes.

**Why.** The edge and the attribute are one fact by construction —
`integrations/proxmox/enrichment.py::domains_of` reads the domain-to-workload
pairs *back off the annotations* precisely so "the graph edge and the resource
attribute cannot disagree", and `platform/estate/discovery/enriched.py`
builds the edge from `resource.attributes["domain"]`. So they carry the same
answer, and the attribute is reachable from a page of resources the caller
already holds, while the edge needs a graph round trip and a deployment with
graph storage available. Resolution stays a pure function of the resources it is
given, which is what lets 062's routing rules and a detector use it.

<!-- proof: tests/unit/platform/estate/test_alert_resolution.py::test_a_blackbox_target_resolves_through_the_declared_domain -->

---

## 5. Unresolved targets are read back off the incidents, not kept in a store

**Not in the plan.** T-002 says the finding is "stored with the incident and
visible via the API"; T-003 says it renders beside 053's divergence entries. It
does not say where the listing comes from.

**Done.** `GET /v1/estate/unresolved-alert-targets` queries live alert incidents
and returns the subjects carrying the `unresolved-target:` prefix, deduplicated
by target and newest first, bounded by `MAX_UNRESOLVED_ALERT_TARGETS`.

**Why not a store of its own.** The finding exists only because an alert
arrived, and the incident is already the record that it did. A second store
would be a second thing to retain, expire and reconcile, and the first time the
two disagreed nobody would know which was right.

**Why under `/v1/estate/` rather than `/v1/incidents/`.** It is a fact about the
estate — the same class as the reconciliation divergence beside it on the same
screen — and `/v1/incidents/unresolved-alert-targets` would have had to be
declared before `/v1/incidents/{incident_id}` to avoid being swallowed by the
path parameter, which is a routing-order trap rather than a decision.

---

## 6. The delivery permission is enforced by a bearer path the router adds, not by the route table

**Planned.** T-006: a minimal webhook-delivery permission, grantable to a
machine token, granting nothing more.

**Done.** `Permission.WEBHOOK_DELIVER`, held from `responder` upward,
`POST /identity/tokens` gained a `permissions` list, and the webhook handler
tries a machine token **after** every configured verifier has declined.

**Why the ordering is load-bearing.** `SharedSecretVerifier` for Alertmanager,
Grafana and Opsgenie reads the same `Authorization: Bearer` header. Trying the
token first would 401 every shared-secret delivery this build already accepts.
Trying it last makes the whole thing additive: all 27 existing webhook tests
pass untouched.

**Why the route table has no row for it.** `WEBHOOK_ROUTES` declares the seven
paths public, and that is still right: a signature-verified delivery carries no
NinjaSRE principal and never will. A guard on the route would refuse exactly
those. The permission is checked inside the handler, at the node the token was
issued for, and the comment on `WEBHOOK_ROUTES` now says so.

**Why `responder` and not lower.** A delivery opens an incident and starts a
run. `viewer` holds no write at all, and
`test_a_viewer_holds_no_permission_that_writes` would have failed — correctly:
a leaked read credential must not become an ingestion endpoint.

**One thing the plan asked for that turned out already true.** "The panel drives
the existing token issuance and shows the secret once, in 058's show-once
pattern" — `POST /identity/tokens` already returned the secret exactly once and
the store already held only a hash. What was missing was the *scope* argument on
the route, which is added here and refuses an unknown permission name rather
than dropping it (a dropped scope silently widens the token).

<!-- proof: tests/unit/gateway/webhooks/test_delivery_permission.py::test_the_same_token_cannot_read_the_run_history -->
<!-- proof: tests/unit/gateway/webhooks/test_delivery_permission.py::test_the_permission_is_grantable_through_the_token_route -->

---

## 7. The ingress URL comes from the request, and the panel lives on `/catalogue`

**Not in the plan.** `plan.md` §A says the panel renders "the URL (`POST
/webhooks/alertmanager` at the deployment's address)" without saying where that
address comes from.

**Done.** `GET /v1/ingress/sources` builds each URL from `request.base_url`.

**Why.** An operator reading the panel reached the deployment at some address,
and that is the address that works. A configured public URL would be a second
copy of the same fact, correct until somebody put the deployment behind a
different name and forgot this one — and the failure would be an operator
pasting a URL that resolves to nothing.

**Where it lives.** The catalogue screen, which is the console's
integrations surface, guarded by `integration.manage` — the same permission the
integration panel beside it uses, because connecting a source is the same act.
T-007 says it lives there until 062 gives it the Data screen.

**What is on it.** Per source: the absolute URL, the body that receiver parses,
and how a delivery is trusted — all three declared on the shipped
`WebhookSourceProfile` rather than in the console, so the shape the adapter
parses and the shape the console claims it parses are one fact. Plus a button
that mints a delivery-scoped token and shows it once.

<!-- proof: tests/unit/gateway/http/test_ingress_routes.py::test_each_source_says_where_to_post_and_what_to_post -->
<!-- proof: console/tests/unit/surfaces/ingress.test.tsx -->
<!-- proof: console/tests/unit/surfaces/delivery-token.test.tsx -->

---

## 8. T-008's scenario did not fail before the wiring, and that is the finding

**Planned.** T-008: "Confirm it fails before the wiring (the scenario *is* the
failing test), then wire whatever the failure names — in 053/054 modules, not in
prompts."

**Done.** The scenario was written and passed on its first run.

**Why, and it is not a bad sign.** Everything T-008 measures about the
*investigation* was already built: the pipeline records evidence with its
source, the diagnosis carries claims with evidence ids, `validated_claims` is
already the set whose citations the run holds, and `replay` already reconstructs
a run from its events. What was missing was upstream of all of it — nothing
turned an alert into a resource — and that is what T-001 and T-002 built. The
scenario is therefore a regression test for a property the platform already had
rather than a specification of one it lacked, and saying so is more useful than
pretending otherwise.

**What is genuinely measured, and it did fail.** The ablation.
`test_with_the_guests_number_absent_the_alert_resolves_to_nothing` and
`test_a_guest_with_no_identifier_turns_the_pressure_source_into_a_named_gap` are
the mechanical arms: remove the guest's number from the alert's labels and
resolution produces a finding instead of a resource; remove it from the estate
and 054's map turns the one question that can answer container pressure into a
named gap. Both would have been impossible to state before this feature, because
`resolve_alert` did not exist.

**Scenario suite delta.** The corpus in `tests/synthetic/conftest.py` goes from
three scenarios to four (`oom-kill`, `deploy-regression`, `chatter`,
**`container-pressure`**). The new one is the first that requires more than one
integration to answer at all: its three backends each hold a third of the
question by construction, so a conclusion drawn from one of them fails
`test_the_claims_between_them_reach_every_source_the_run_used`. The whole
synthetic suite is 644 passing, in 8.4s, and two consecutive runs agree.

---

## 9. The live cluster run has not happened, and could not from here

**Planned.** T-011 and Definition of done 1: point HAL9000's Alertmanager at the
deployment, fire a test alert, and record the time from firing to run creation,
the resolved resource, the evidence sources and the replay output.

**Not done.** There is no cluster and no deployment reachable from this machine.
`/root/infra-cluster` does not exist, nothing here holds an address or a token
for a Proxmox node or for the Alertmanager at 10.20.20.36, and
`test_no_proxmox_test_reaches_a_live_cluster` asserts the suite stays that way.
This is the third feature in a row to record the same sentence (053 §12, 054
§11), and it is the same machine each time.

**What is proven instead.** Every mechanism the criterion names, offline, end to
end: a delivery authenticated by a token that can do nothing else reaches the
handler, the alert resolves against a stored estate, the incident points at the
resource, the run starts with it in context, and the whole thing replays. What
is unproven is the *wall clock* — that a real Alertmanager reaches a real
deployment inside a minute — and the shape of the real cluster's guests.

**What running it needs, exactly.** A deployment reachable from 10.20.20.36; a
delivery token from the panel (`/catalogue` → "Where to send alerts" → "Issue a
delivery token"); a `webhook_config` in the `infra-cluster` repository pointing
`url` at `<deployment>/webhooks/alertmanager` with
`authorization: {type: Bearer, credentials: <token>}`, applied by `./infra`; and
`amtool alert add` to fire one. Then `GET /v1/runs?trigger=alert` for the
creation time and `GET /v1/runs/{run_id}/replay` for the transcript.

<!-- handoff: to=062-data-ingress-and-delivery what="run the whole alert path against the live HAL9000 cluster once — point its Alertmanager at the deployment, fire a test alert, and record firing-to-run latency, the resolved resource, the evidence sources and the replay output" -->

---

## 10. The two handoffs this feature was given

### 10.1 — 053's live onboarding run (`d9cd9fd4`): re-deferred

053 asked this feature to run the onboarding against the live HAL9000 cluster
and its `infra-cluster` repository once, and record the real per-zone counts
against the fixture's declaration.

**Not done, for the reason in §9**: there is no cluster reachable from this
machine and no `infra-cluster` checkout on it. Nothing about this feature's work
changed that — 055 needs a live cluster for its *own* acceptance criterion 1 and
could not get one either.

Re-deferred rather than silently dropped. It goes to 062, which is the feature
that owns the ingress-and-delivery surface and therefore the first one whose
acceptance genuinely requires a deployment something outside can reach.

<!-- handoff-done: id=d9cd9fd4 -->
<!-- handoff: to=062-data-ingress-and-delivery what="run the 053 onboarding against the live HAL9000 cluster and its infra-cluster repository once, and record the real per-zone counts against tests/support/proxmox_estate.py's declaration" -->

### 10.2 — 053's first-day browser project (`8965f981`): re-deferred

053 asked this feature to run the first-day browser project against the compose
backing on a machine whose docker build network can reach the Apache AGE
release, and against a validation container once one exists.

**Not done.** The build network on this machine is the same one 053 met, and no
validation container exists yet — nothing in this feature creates one, and
inventing one to satisfy a handoff would be building the wrong thing to close a
mark.

Re-deferred to 062 for the same reason as 10.1: it is the next feature whose own
acceptance needs a deployment reachable over a network, so it is the first one
where the environment this asks for is a cost it was going to pay anyway.

<!-- handoff-done: id=8965f981 -->
<!-- handoff: to=062-data-ingress-and-delivery what="run the first-day browser project against the compose backing on a machine whose docker build network can reach the Apache AGE release, and against a validation container once one exists" -->

---

## 11. Two checkers learned about a subject that is not a resource, and neither was loosened

**Not in the plan.** Adding `unresolved-target:` as an incident subject broke two
referential checks that had no vocabulary for it.

**Done.**

- `tools/mockplane/verify/referential.py` gained `unresolved-target` as a member
  of the `subject` union, populated from the ingress fixture's own targets, and
  the `detector` namespace gained every member of `ALERT_SOURCES` (eight, not
  the seven webhook *paths* — the catalogue also carries `webhook` and
  `plain_text`) — because an incident's `detector` field is its *origin id*,
  which the gateway's own view documents as "the detector, the alert source, or
  the person who opened it".
- `platform/startup/demo/dataset.py::unresolved_references` skips a subject
  carrying the prefix.

**Why this is not a loosened gate.** Both changes *declare a case* rather than
remove a check. The mockplane one adds two namespaces and keeps every existing
assertion; the demo one is pinned by a new test that fails if the dataset stops
carrying the case, so the exemption cannot quietly become a hole. Demanding that
an unresolved target resolve to a resource would be demanding the finding be
about the very thing whose absence it reports.

<!-- proof: tests/unit/platform/startup/test_demo.py::test_an_unresolved_alert_target_is_a_subject_that_resolves_to_nothing_on_purpose -->

---

## 12. Alert resolution reads one page of the estate per delivery

**Not in the plan.**

**Done.** `_resolve_against_estate` issues one `EstateQuery(limit=MAX_ESTATE_PAGE_SIZE)`
per verified delivery and resolves against that page.

**Why.** `vmid`, `address` and `domain` are all *attributes*, and `EstateQuery`
has no attribute dimension. Adding one is a repository change — both backends,
the contract suite, the port — for a read that is already bounded, on a path
that is already rate-limited and load-shed. This is the same bound 053 recorded
for enrichment (§9 there), and the same cursor 062 was already asked for covers
both.

**What it costs, said plainly.** An estate larger than `MAX_ESTATE_PAGE_SIZE`
resolves an alert against its first page, so a guest beyond it produces an
unresolved finding rather than a resolution — a false finding, not a false
resource. The reference cluster is 57 guests plus two nodes.

---

## 13. Test-first, and the one place it was not

Every module here landed test-first with the failure confirmed: T-001
(`ModuleNotFoundError`), T-002 (`ImportError` on the prefix constant), T-003 (two
red console assertions), T-004 (three red), T-006 (seven red), T-007 (four red
console, five red gateway), Phase 4 (`ImportError` on the scenario).

The exception is §11 — the two referential checkers. Those were changed in
response to a *failing existing test* rather than a new one, which is the same
discipline arrived at from the other direction; the demo one then gained its own
test pinning the exemption, and the mockplane one is covered by the existing
`test_every_reference_in_every_scenario_resolves` over a dataset that now carries
the case.

`tests/synthetic/test_first_investigation.py` is the honest partial exception,
and §8 says why in full: the scenario passed on its first run because the
investigation machinery it measures already existed. Its ablation arms did fail
first, because `resolve_alert` did not exist to run them against.

---

## 14. Gate

`make verify` is green: **13,059 passed, 25 skipped**, 6m35s. That includes the
full console gate — lint, types, unit suite at 94.67% statements and 90.21%
branches, build, budgets, end-to-end, and the visual baselines.

Six visual baselines were recaptured (`console-visual-accept`) and are committed
as a reviewable change: `resources-1440-light` and `resources-320-light` gained
the "Alerts for things not here" panel, and the four `shell-*` captures moved
because the dataset gained an alert-origin incident and the notification count
with it.

`make test-postgres` has **not** been run. Nothing here touches
`platform/persistence/` — no port, no repository, no migration — so the rule
that gate exists for is not engaged. The one storage-adjacent change is a new
read composed from existing ports in a route.

---

## 15. What the done-audit found

Run against the whole branch diff. It confirmed items 2, 3, 4 and 5 met by
tests that assert behaviour rather than fixture construction; confirmed item 1
as honestly reported undone; confirmed every `<!-- proof: -->` mark resolves to
a real test (70 collected, 70 passing, plus 22 console tests); confirmed both
handoff ids were computed correctly and are closed and re-deferred; and
confirmed no gate configuration was loosened and no `skip`/`xfail` was added.

It found two things, and both are fixed rather than argued with.

**One real gap, in item 6.** The replay criterion names
`GET /v1/runs/{run_id}/replay` in both `spec.md` and `tasks.md`, and the test I
cited exercised `core.pipeline.streaming.replay` over an in-memory sink — a
different mechanism, over a different type, reached without the route or the
store. It was following the pattern
`tests/synthetic/test_investigation_end_to_end.py` established, which is why it
looked right; it was still not what the criterion says. §16 records the fix.

**One factual error in this file.** §11 said "the seven alert sources" where the
code adds eight; corrected above. The mechanism was right and the sentence was
not.

---

## 16. Item 6 is now proven against the route the specification names

**Found by the audit**, not by me, and worth recording in those terms.

`tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_run_the_alert_started_replays_from_its_own_recorded_events`
drives the whole path the criterion describes: a verified Alertmanager delivery
creates a run, the run records a turn and a capability call through the same
`RunRecorder` the real investigation uses, and `GET /v1/runs/{run_id}/replay`
reconstructs it from the persisted trace alone — through
`uow.run_traces.replay` and `platform/runs/replay.py::replay_trace`, which is
what the route actually does. A second test,
`::test_the_replayed_run_is_the_one_the_alert_created`, pins that the run in
question is the alert's: trigger `alert`, carrying the fingerprint as its
`alert_id`.

The stand-in is the investigation *body*, which is what
`FakeInvestigationRunner` already is throughout this suite. What is no longer a
stand-in is the route, the store, or the reconstruction.

The synthetic test stays, because it proves a different and also useful thing —
that the pipeline's own event stream reconstructs the stages, the tool calls and
the evidence ids of the container-pressure run. The two together are the whole
of the criterion; either alone is not.

<!-- proof: tests/unit/gateway/webhooks/test_alert_ingress.py::test_the_replayed_run_is_the_one_the_alert_created -->

---

## 17. The close failed on a browser test, and the reading varied with the machine

`make close-task` ran `make verify` again and the console gate went red on one
test out of sixty:

```
[behaviour] › tests/e2e/shell.spec.ts:97 › a signed-in operator
             › opens the palette from the keyboard and navigates with it
    Error: expect(locator).toBeVisible() failed
    Locator: getByTestId('palette')   Expected: visible   Timeout: 5000ms
    Error: element(s) not found
```

Nothing in this feature touches the shell, the palette or the dashboard. The
failing test's 5.2s is 5s of timeout plus a 0.2s page load, so the page was up
and quick and the keystroke simply did nothing.

### What it actually is, measured rather than guessed

The shortcut is a `keydown` listener the shell attaches from a `useEffect`, so
it exists only once React has hydrated. `page.goto` resolves on `load`, which
says the document finished — not that the listener is on the window. Between the
two there is a gap, and a keystroke fired into it is lost, because nothing
re-sends a keystroke.

Confirmed from inside the page rather than inferred. A throwaway probe installed
a capturing `keydown` recorder via `addInitScript`, then did exactly what the
test does — `goto('/')`, one `Control`+`K`, look for the palette — sixty times
with eight busy loops occupying the machine:

```
PROBE MISS opened=false keydownsSeen=1     (×3 of 60)
```

`keydownsSeen=1` is the finding. The browser dispatched the keydown to the
window every single time; three times out of sixty the window had no listener on
it yet. So the varying reading is not a slow console, a lost event or a flaky
locator — it is the ~5% of loads on a contended machine where `load` wins the
race against React's hydration callback.

Not reproducible any other way tried: the palette test alone passes 5/5, the
whole `behaviour` project passes twenty consecutive times
(`make console-e2e-sweep`, 20 × 60 green), and CDP CPU throttling up to 20×
never reproduces it, because throttling slows `load` and hydration equally. Only
real contention — several agents on one machine, which is what `close-task` met
— separates them.

### The fix, and why it is not a loosened assertion

`openPalette(page)` in `console/tests/e2e/shell.spec.ts` presses the shortcut
until the palette answers, inside `expect(...).toPass()`. The palette must still
open from the keyboard and from nothing else; what is no longer asserted is that
the console was already listening at the instant `load` fired, which was never a
claim about the console.

Both palette tests use it, and the second is strictly stronger for it.
`dismisses the palette without changing the page` used to press `Control`+`K`,
press `Escape`, and assert `toHaveCount(0)` — an assertion that also passes when
the palette never opened at all. It could not fail for the reason it exists, and
it did not fail on the run that caught the sibling. It now opens the palette for
real before dismissing it.

### What was deliberately not done

- **No retry, no `skip`, no timeout raised.** `retries: 0` and `workers: 1`
  stand, and no gate configuration was touched.
- **No change to the console.** A shortcut that does nothing until the script
  behind it has run is true of every keyboard shortcut in every browser
  application, and the frame this deployment promises before any script has run
  is the static one `the first paint › carries the whole frame before any script
  has run` already pins. Buffering pre-hydration keystrokes in an inline script
  would be a new behaviour, invented to close a mark rather than because
  somebody wants it.
- **Not handed on.** There is nothing left to do: the defect was in the test's
  assumption, and the assumption is gone.

### Verification

120 executions of the two palette tests under eight busy loops — the condition
that produced 3 misses in 60 before the change — with no failure. At the
measured 5% rate, 120 clean executions by luck is about one chance in five
hundred.

Then `make verify` green end to end: **13,061 passed, 25 skipped**, 6m35s, plus
the whole console gate — 1,168 console unit tests, the `behaviour` project 60/60,
`first-day` 5/5, the visual baselines unchanged. The count is two above §14's
because §14 was written before the last two test commits on this branch.

<!-- proof: console/tests/e2e/shell.spec.ts::opens the palette from the keyboard and navigates with it -->
<!-- proof: console/tests/e2e/shell.spec.ts::dismisses the palette without changing the page -->
