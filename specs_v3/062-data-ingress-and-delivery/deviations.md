# Deviations — 062 Ingress and delivery

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each acceptance criterion is proven

| Criterion | Where it is proven |
|---|---|
| 1 — each ingress route shows URL, token, format and the last delivery with date, outcome and masked sample | `tests/unit/gateway/http/test_transit_routes.py::test_a_row_names_the_url_the_format_and_the_last_delivery`, `::test_the_masked_sample_rides_on_the_row`, `console/tests/unit/surfaces/ingress.test.tsx`, `console/tests/unit/surfaces/data.test.tsx::a source that has delivered` |
| 2 — a configured source that never delivered appears as such, without hunting | `tests/unit/gateway/http/test_transit_routes.py::test_every_configured_receiver_appears_whether_or_not_it_ever_delivered`, `console/tests/unit/surfaces/data.test.tsx::a source that has never delivered`, `console/tests/e2e/surfaces.spec.ts::a silent receiver is the first thing on the transit screen` |
| 3 — a routing rule is simulated against a real payload before saving, showing rule, team and action | `tests/unit/gateway/http/test_transit_routes.py::test_a_pasted_payload_is_simulated_against_the_rules_before_anything_is_saved`, `console/tests/unit/surfaces/simulation.test.tsx`, `console/tests/e2e/surfaces.spec.ts::a rule cannot be saved until its effect has been seen` |
| 4 — the fate of what matched nothing is explicit and visible | `tests/unit/platform/ingress/test_rules.py::test_a_set_without_a_catch_all_last_is_refused`, `tests/unit/platform/config_service/test_transit_section.py::test_a_rule_set_with_no_explicit_last_word_never_reaches_storage`, `console/tests/unit/surfaces/data.test.tsx::the rules` |
| 5 — a destination declares events, channel and detail level, and shows its masking policy | `tests/unit/gateway/http/test_transit_routes.py::test_a_destination_declares_its_events_channel_detail_and_masking_policy`, `console/tests/unit/surfaces/data.test.tsx::the destinations` |
| 6 — a failed delivery shows its reason and can be re-sent | `tests/unit/gateway/http/test_transit_routes.py::test_a_failed_delivery_can_be_sent_again_and_the_ask_is_audited`, `console/tests/unit/surfaces/resend.test.tsx`, `console/tests/e2e/surfaces.spec.ts::a report that did not arrive can be sent again from the row it failed on` |
| 7 — given a finding, the interface answers which query, origin and instant it came from | `console/tests/unit/surfaces/data.test.tsx::provenance`, `console/tests/e2e/surfaces.spec.ts::an arrival answers which rule caught it and which run it became`. See §9 for what the drawer answers itself and what it hands over to |

<!-- proof: tests/contract/persistence/test_transit_ledger.py::test_the_last_delivery_reaches_outside_the_counting_window -->
<!-- proof: tests/unit/gateway/webhooks/test_transit_ledger_on_ingress.py::test_an_unverified_delivery_is_a_row_with_its_reason -->
<!-- proof: tests/unit/gateway/webhooks/test_transit_ledger_on_ingress.py::test_the_stored_sample_has_been_through_the_masking_policy -->
<!-- proof: tests/unit/gateway/webhooks/test_routing_rules_on_ingress.py::test_a_discarding_rule_stops_the_investigation_and_leaves_the_reason -->
<!-- proof: tests/unit/gateway/webhooks/test_post_verification_behaviour.py::test_a_verified_delivery_starts_an_investigation -->
<!-- proof: tests/unit/gateway/http/test_transit_routes.py::test_every_configured_receiver_appears_whether_or_not_it_ever_delivered -->
<!-- proof: tests/unit/gateway/http/test_transit_routes.py::test_a_pasted_payload_is_simulated_against_the_rules_before_anything_is_saved -->
<!-- proof: tests/unit/gateway/http/test_transit_routes.py::test_a_failed_delivery_can_be_sent_again_and_the_ask_is_audited -->
<!-- proof: tests/unit/platform/ingress/test_rules.py::test_a_set_without_a_catch_all_last_is_refused -->
<!-- proof: tests/unit/platform/delivery/test_dispatch.py::test_the_body_passes_the_masking_policy_before_it_leaves -->
<!-- proof: tests/unit/gateway/webhooks/test_alertmanager_delivery_identity.py::test_a_resolution_of_the_group_the_firing_opened_closes_its_incident -->
<!-- proof: tests/contract/persistence/test_estate_repository.py::test_a_whole_estate_pass_reaches_past_one_page -->

---

## 1. The port is the **seventeenth**, not the fourteenth

**Planned.** `plan.md` §A.1 and "Verificação de constituição XI": "the
fourteenth port, with every port-count assertion and document updated in the
same commit".

**Done.** It is the seventeenth. The count was already sixteen when this feature
started — `plan.md` was written against an older tree, and 054's signal store
and incident store and 057's remediation ledger had all landed since.

**What was actually updated in that commit**, which is the part the plan cared
about: `platform/persistence/ports/__init__.py`'s table and prose,
`ports/transaction.py`'s three counts, `fakes/gateway.py`,
`fakes/__init__.py`, `postgres/gateway.py`, `AGENTS.md`'s non-negotiables table
(which still said *thirteen*, two features out of date), and
`tests/unit/platform/persistence/test_port_conformance.py`, whose test is now
named `test_the_specification_names_exactly_seventeen_ports`.

No document enumerates the ports by name outside `ports/__init__.py`, which is
why the doc-drift check had nothing to say.

---

## 2. Transit is a **seventh configuration section**, not a corner of an existing one

**Not in the plan.** `plan.md` §B says "a configuration section (058's tree)"
without saying which.

**Done.** `RootConfig` gained `transit`, holding `rules` and `destinations`, and
`ROOT_SECTIONS` went from six to seven.

**Why not under `policies`.** The whole argument of `spec.md` is that "what
value applies here" and "where did this come from and where did it go" are
different questions, and that mixing them is how an operator ends up opening
five screens. Putting the routing rules in with the thresholds would have been
the mixing, in the one place the feature exists to un-mix.

**What it cost, and it is the honest reason to have hesitated.** `ROOT_SECTIONS`
is load-bearing: it is what `section_fields()` walks, what the console's
configuration form renders from, and what the closed-schema argument rests on.
Seven is a bigger surface than six. The alternative was a section that reads as
policy and is not one.

---

## 3. A rejected delivery with no verified route is recorded against the **first configured route's** organisation

**Not in the plan.** T-002 says the handler writes the ledger "on every path,
including refusals". It does not say which tenant an unauthenticated refusal
belongs to, and the ledger is tenant-scoped.

**Done.** `_ledger_refusal` writes against `source_routes[0].org_id`. A path
with no configured route writes nothing, and the existing warning in the log is
the whole of the record.

**Why the first rather than all of them.** A refusal is a fact about the
*endpoint*, and the endpoint's owner is whoever configured it. Writing one row
per tenant would multiply an *unauthenticated* request's storage cost by the
number of tenants configured on that path, which is a denial-of-service surface
rather than a feature — somebody who can reach the URL should not be able to
choose how many rows their request writes.

**What this costs in a genuinely multi-tenant deployment**, said plainly: a
second organisation's operator does not see an unverified delivery aimed at
their verifier. They see every delivery that *verified* against it, which is the
half attributable to them. Every deployment this has run against is
single-tenant.

---

## 4. A sample is kept only for a **verified** delivery

**Not in the plan.** §A.1 says a masked sample of the last payload per source,
without saying whose payload.

**Done.** `_Ledgering.sample` is set after verification succeeds. An unverified
sender leaves a ledger row and no sample.

**Why.** A sample is rendered on a screen an operator reads. Keeping one from an
unverified sender would let anybody who can reach the URL put text of their
choosing in front of an operator, stored, at their leisure. Not being able to
see what an unverified sender sent is a smaller loss than that.

**The one exception, and it is deliberate.** A body that verified and then
*failed to parse* is sampled. "Did the format change" is exactly the question a
parse failure raises, and refusing to answer it in the one case it is being
asked would make the sample useless.

<!-- proof: tests/unit/gateway/webhooks/test_transit_ledger_on_ingress.py::test_an_unverified_sender_leaves_no_sample -->
<!-- proof: tests/unit/gateway/webhooks/test_transit_ledger_on_ingress.py::test_a_body_that_would_not_parse_is_sampled_anyway -->

---

## 5. A shed storm is **one row per window**, not one row per refusal

**Planned.** T-002: the handler ledgers "accepted, rejected (with reason), shed,
duplicate".

**Done.** Shed deliveries are ledgered — as one row per `(source, team, shed
window)`, carrying how many were dropped, refreshed every
`TRANSIT_SHED_LEDGER_INTERVAL` (100) sheds rather than on every one.

**Why, and it is not only about cost.** A load shedder exists to bound the work
a storm can cause. A row per refused request would move that work into the store
instead of removing it — the shedder would become the most expensive step on the
path it exists to cheapen, and the table would grow exactly as fast as the storm
it is recording. A storm is *one fact*; the count is what makes it legible.

**Measured.** `test_a_1000_event_storm_is_bounded_with_a_complete_shed_record`
went from 3.5s to 46s with a row per shed and back to ~17s with the window row;
the residue is the in-memory fake, which deep-copies the whole tenant state per
transaction, so a table that has grown makes every later transaction slower.
Against Postgres each of these is one `INSERT … ON CONFLICT`.

**What it costs.** While a storm is running, the count on the row trails by up
to 99 deliveries. It is exact once the storm stops. Stated on the constant.

<!-- proof: tests/unit/gateway/webhooks/test_transit_ledger_on_ingress.py::test_a_shed_storm_is_one_row_carrying_how_many_were_dropped -->

---

## 6. The idempotency window is **shorter** than the deduplication window, and that is the fix

**Handoff `0b777e65`, from 055.** Derive an Alertmanager delivery identifier
instead of using `groupKey`, so a re-notification of an unchanged group links to
the open investigation rather than answering as a duplicate delivery.

**Done, and it took two changes rather than one.**

**The identifier.** `alertmanager._event_id` is now
`groupKey@sha256(status + each alert's fingerprint, status, startsAt, endsAt)`.
A byte-identical retry derives the same id and is still one delivery; a
notification saying anything *new* about the group derives a different one. That
alone fixes the defect 055 named in as many words: Alertmanager sends the same
`groupKey` for the resolution, so the resolution was being answered "already
processed" and the incident the firing opened never closed. 055's own tests had
to vary `groupKey` — something a real Alertmanager never does — to get around it.

**The window, which the plan did not anticipate.** An *unchanged* group
re-notified after `repeat_interval` is genuinely indistinguishable from an HTTP
retry: Alertmanager sends no per-notification identifier and no send timestamp.
So no identifier can separate them, and the thing that can is the window. The
idempotency index now uses `WEBHOOK_DELIVERY_RETRY_WINDOW_SECONDS` (60s — the
length of an HTTP retry) instead of `ALERT_DEDUP_WINDOW_SECONDS` (600s). A later
notification therefore falls out of idempotency while still inside deduplication,
and is *linked to the open investigation* — which is the sentence the handoff
asked for, and which was unreachable while the two windows were the same length.

All 27 pre-existing webhook tests pass untouched.

<!-- handoff-done: id=0b777e65 -->
<!-- proof: tests/unit/gateway/webhooks/test_alertmanager_delivery_identity.py::test_a_re_notification_outside_the_retry_window_links_rather_than_repeats -->
<!-- proof: tests/unit/gateway/webhooks/test_alertmanager_delivery_identity.py::test_a_resolution_is_not_the_same_delivery_as_its_firing -->

---

## 7. The estate cursor, and the three passes that were quietly truncated

**Handoff `f1abe4cb`, from 053.** Give `EstateQuery` a cursor so enrichment and
any other whole-estate pass can page beyond `MAX_ESTATE_PAGE_SIZE` instead of
reporting truncated.

**Done.** `EstateQuery.after` is a keyset cursor over the `resource_id` ordering
`query` already returns — not an offset, because an estate grows underneath an
offset and an offset-paged sweep would skip whatever was inserted before its
cursor. `whole_estate(repository, query)` pages on it, bounded by
`MAX_ESTATE_SWEEP_PAGES` (50, so 25,000 resources at the page bound).

**Three callers moved, and the third is the one that mattered most.**
`platform/estate/enrichment.py` (the one the handoff names),
`platform/estate/discovery/enriched.py` (which builds the topology graph — a
graph from the first page is a graph missing edges nobody can see are missing),
and `gateway/webhooks/router.py::_resolve_against_estate`. That last one is 055
§12's recorded cost: an alert about a guest beyond the first page produced an
unresolved finding *for a resource that was there*. A false finding is worse
than a slow read.

**Why it returns what it read at the ceiling rather than raising.** A caller
enriching four thousand resources wants the four thousand it got, and
`len(...) == max_pages * limit` is how it can tell it did not reach the end.

<!-- handoff-done: id=f1abe4cb -->
<!-- proof: tests/contract/persistence/test_estate_repository.py::test_a_cursor_resumes_where_the_last_page_stopped -->
<!-- proof: tests/contract/persistence/test_estate_repository.py::test_a_whole_estate_pass_stops_at_its_page_ceiling -->

---

## 8. The change ruler was reading a field the deployment never sends

**Handoff `d4a9ac75`, from 057.** Put a `changes_in_window` call into the
committed run-replay fixture and capture a visual baseline for the run screen's
change ruler.

**Done, and it found a defect on the first run — which is the whole value of the
handoff.** `console/src/surfaces/changes.ts` read each change's instant from
`entry.instant`. The capability's result carries `occurred_at`:
`platform.changes.models.Change.to_record` serialises that name, and
`ChangeInquiry.to_record` spreads it. `instant` existed only in
`run-timeline.test.tsx`, which invented the shape it was testing against — so
the ruler was correct against its own fixture and **blank against a real
deployment**, and no test could see it.

**Both are fixed.** `changes.ts` reads `occurred_at`; the component test's two
change records were corrected to the real field. `run-0001`'s committed replay
now carries a real `changes_in_window` call with two graded changes — one
`manages_resource`, one `window_only` — written in
`ChangeAnswer.to_record`'s shape.

**The baseline.** `run-detail-1440-light` and `run-detail-1440-dark` were
recaptured and now contain the ruler: the statement, the two marks with the
temporal coincidence drawn as weakly as it was graded, the window, and both
changes named beneath it. The acceptance record on the light one says so, which
is what makes a regression in the *emphasis* — the thing the ruler has to get
right — something the gate can catch.

<!-- handoff-done: id=d4a9ac75 -->
<!-- proof: console/tests/unit/surfaces/run-timeline.test.tsx -->

---

## 9. The provenance drawer answers transit itself and **hands over** for the rest

**Planned.** T-013 and acceptance 7: "from an ingress row to rule, team, and
run; from a finding to its query/origin/instant via the trace link".

**Done.** The drawer on each ingress row answers the first half from the ledger
rows the screen already read: arrived by, rule, team, resource, and a link to
the run. The second half is the link.

**Why the second half is a link and not a rendering.** Every finding in a run
already names the query, the origin and the instant it came from — that is the
investigation's own evidence attribution, built long before this feature. A
second rendering of it on this screen would be a second opinion about the same
trace, and the first time the two disagreed nobody would know which was right.
The chain does not stop at the drawer; it hands over to something that exists.

**One thing worth naming.** The drawer is built from the ledger page the screen
already holds rather than from a query per source. A read per receiver would
make the screen's cost a function of how many an operator wired up.

---

## 10. The masking policy is resolved **per delivery**, from the configuration tree

**Not in the plan.** §A.1 says the sample is stored "after the masking policy"
without saying whose.

**Done.** `_settings` resolves the routed team's effective configuration through
`ConfigService` on each verified, admitted delivery, and
`bindings.masking_policy` turns it into the policy the sample passes through.
The level is written onto the sample.

**Why per delivery rather than held on `GatewayState`.** It is the pattern every
other route in `gateway/http/routes/` already follows, and it is what makes "a
rule an operator added thirty seconds ago decides the next delivery" true. A
policy cached on the process would make "when does this take effect" a question
about process lifetime.

**Where it sits on the path, and why that moved.** Originally before the parse;
now after the shed check, so a storm past the rate limit costs an idempotency
lookup and a window check and nothing else. A rate limiter that was the most
expensive step on the path would be doing the work it exists to refuse.

**The fallback chain.** Team node, then organisation root, then shipped
defaults. Falling straight to the defaults when a verifier names a team the tree
has no node for would silently ignore rules an operator wrote one level up.

---

## 11. Outbound delivery has no transport, and says so

**Planned.** `plan.md` §C: "no new outbound integrations — the destination
concept binds whatever delivery-capable integrations the catalogue has".

**Done, and the honest consequence is stated in the record.**
`DeliveryDispatcher.transport` is supplied by the composition root, exactly as
the gateway's model and deep verifiers are. Nothing composes one yet, so every
attempt in this build fails with "this deployment has no transport wired for
outbound delivery; the message was composed and not sent" — a *visible* failed
delivery with a reason and a re-send control, rather than a success nobody
receives.

**Why not compose one.** Reaching a chat platform means a client and a
credential proxy. A dispatcher that built one out of ambient configuration would
be posting into a workspace nobody chose, and inventing an integration to make a
screen look finished is building the wrong thing to close a checkbox. The
composition seam is the whole of what this feature owes; the transport belongs
with whoever wires the chat sink to the proxy.

**What a deployment with no channel sees.** The destination column reports
`NO_DELIVERY_CHANNEL_REASON` once, at the top, rather than rendering rows that
would silently never send — the 054 known-gap posture, which is what T-010 asks
for.

<!-- handoff: to=063-outbound-transport what="wire a chat transport into DeliveryDispatcher at composition, so a declared destination actually receives what it subscribed to instead of a failed attempt naming the missing transport" -->

<!-- proof: tests/unit/platform/delivery/test_dispatch.py::test_a_deployment_with_no_transport_fails_visibly_rather_than_silently -->
<!-- proof: tests/unit/gateway/http/test_transit_routes.py::test_a_deployment_with_no_channel_says_why_destinations_cannot_be_configured -->

---

## 12. The `/data` screen absorbed 055's ingress panel, and the catalogue lost it

**Planned.** T-011: "055's ingress panel absorbed here".

**Done.** The paste-ready address, the expected body, the verification sentence
and the delivery-token control moved from `/catalogue` to the ingress column of
`/data`, and `console/tests/unit/surfaces/ingress.test.tsx` moved with them —
same assertions, rendered against `DataScreen`.

**Why the whole panel rather than a copy.** The panel says what to paste and the
column says whether anything arrived. They are two halves of one question, and
the operator asking it is standing on one screen.

**What this cost in baselines.** `catalogue` has no visual baseline, so nothing
was recaptured for the loss; every screen that draws the sidebar was recaptured
because the navigation gained an entry.

---

## 13. A comment inside a route-manifest entry makes the area invisible to the gate

**Found, not planned.** `tests/contract/console/test_console_shell.py` parses
`routes.ts` with a regular expression requiring `id:` immediately after the
opening brace. `/data`'s entry originally carried a leading comment and was
therefore *not* in the "declared" set, so the walk-coverage test failed with
`/data` walked but not declared.

**Done here.** The comment moved above the object literal, and a note inside the
entry says why it is there rather than inside.

**Not fixed here, and the reason is that it belongs to somebody else.** The
`first-run` entry has the same shape and is invisible to the same parser — which
is why `/first-run` is absent from `SHELL_PATHS` and the equality test passes.
Tightening the parser would add `/first-run` to the routes the deploy walk must
cover, which is a decision about the guided setup's route rather than about
transit, and making it from here would change a sibling feature's gate on the
way past.

<!-- handoff: to=063-console-route-manifest what="tighten test_console_shell.py's routes.ts parser so a comment inside an entry cannot hide an area from the deploy-walk coverage check, and decide whether /first-run belongs in SHELL_PATHS" -->

---

## 14. The three live-cluster handoffs: re-deferred, for the third time each

053 → 055 → 062 have now each carried these, and the sentence is the same
sentence. There is no cluster and no deployment reachable from this machine:
`/root/infra-cluster` does not exist, nothing here holds an address or a token
for a Proxmox node or for the Alertmanager at 10.20.20.36, and
`test_no_proxmox_test_reaches_a_live_cluster` asserts the suite stays that way.

Nothing about *this* feature changed that. 062 builds the surface that makes a
live run legible — the ledger, the never-delivered flag, the masked sample, the
provenance chain — which is the half that was missing when 055 tried. What is
still missing is the machine.

### 14.1 — the whole alert path against HAL9000 (`a8132ba2`)

**Not done.** What running it needs is unchanged from 055 §9, and this feature
adds one thing to the recipe: after firing, `GET /v1/transit/ingress` answers
firing-to-arrival directly, `GET /v1/transit/deliveries` names the rule and the
run, and the masked sample says what the real Alertmanager actually posted —
which is three of the four things the criterion asks to be recorded, now
readable from one screen instead of reconstructed from logs.

<!-- handoff-done: id=a8132ba2 -->
<!-- handoff: to=063-live-cluster-validation what="run the whole alert path against the live HAL9000 cluster once — point its Alertmanager at the deployment, fire a test alert, and record firing-to-run latency, the resolved resource, the evidence sources and the replay output, reading the first three off /data" -->

### 14.2 — 053's onboarding against HAL9000 (`0ad4f198`)

**Not done**, for the same reason. Worth recording that the estate cursor (§7)
removes one of the things that run would have measured wrongly: the onboarding's
enrichment pass no longer stops at 500 resources, so per-zone counts from a real
cluster are now counts of the cluster rather than of its first page.

<!-- handoff-done: id=0ad4f198 -->
<!-- handoff: to=063-live-cluster-validation what="run the 053 onboarding against the live HAL9000 cluster and its infra-cluster repository once, and record the real per-zone counts against tests/support/proxmox_estate.py's declaration" -->

### 14.3 — the first-day browser project against compose (`12654832`)

**Not done.** The docker build network on this machine is the one 053 and 055
both met, and no validation container exists — nothing in this feature creates
one, and inventing one to close a mark would be building the wrong thing.

Worth saying that the *browser* half now runs here: `make console-e2e` is green
at 68/68 and `make console-visual` at 22/22, both against the mock backing,
after installing the Playwright browser this worktree was provisioned without.
What is unproven is the same thing as before — the compose backing.

<!-- handoff-done: id=12654832 -->
<!-- handoff: to=063-live-cluster-validation what="run the first-day browser project against the compose backing on a machine whose docker build network can reach the Apache AGE release, and against a validation container once one exists" -->

---

## 15. Test-first, and where it was not

Every module landed test-first with the failure confirmed: T-001 (contract suite
red on `ImportError`), T-002 (eleven red assertions before the handler wrote a
row), T-004 (green *before* the seam moved, which is the point of a
characterisation test, and green after), T-005/T-006 (sixteen red rule
assertions, then five red against the live path), T-007/T-008/T-010 (nineteen
red route assertions), T-009 (fifteen red), T-011–T-014 (the console suite red
on a missing screen, then on each missing test id).

The exceptions, both honest:

- **§13**, the route-manifest comment. That was a change made in response to a
  *failing existing test* rather than a new one — the same discipline arrived at
  from the other direction.
- **§8**, the change-ruler field. The defect was found by writing the fixture,
  not by writing a test for it; the correction then landed against the existing
  component test, which had been asserting the wrong shape.

---

## 16. Gate

Green at the time of writing:

```
make lint format-check typecheck check-imports check-constants   all pass
make check-docs check-protocols check-raw-sql check-credentials  all pass
make check-vendor-sdks                                           passes
uv run pytest tests/                                             7m55s
    13,490 passed, 25 skipped, 0 failed — nothing excluded
make console-e2e            68 passed
make console-visual         22 passed
console unit suite          1362 passed, branches 90.14% (floor 90)
```

That final run is the whole of `tests/`, `tests/contract/console` included, after
§18's fix. An earlier run excluded that directory and reported one failure; both
the exclusion and the failure are recorded below rather than edited out, because
the exclusion is the more interesting of the two.

**The earlier failure was a latency budget, measured under contention.**
`tests/benchmarks/test_topology_scale.py::test_a_depth_three_blast_radius_over_ten_thousand_services_stays_bounded`
asserts a wall-clock millisecond budget on a graph traversal. It failed on a run
that was sharing the machine with a second heavy process, passes on its own in
1.5s, and passed again on the uncontended full run quoted above. Nothing in this
diff touches topology, the graph, or anything the traversal reads.

Recording it rather than dismissing it, because "a test that passes only
sometimes is a failing test" is the rule and this one is: its reading is a
function of how busy the machine is. It is not this feature's to fix — the
budget and the measurement both predate the branch — but it is the kind of test
that will keep costing somebody a red gate on a contended machine.

<!-- handoff: to=063-benchmark-contention what="make the topology latency benchmark a measurement that does not vary with how busy the machine is — either by measuring work rather than wall clock, or by taking the best of several passes the way a benchmark normally does" -->

**`make test-postgres` has not been run**, and this feature does touch
`platform/persistence/`: a new port, a new repository, a new migration
(`0010_transit`). The contract suite runs against the fakes here and the
`--postgres` row needs a database this machine does not have. The Postgres
repository is written against the same statements every other repository in that
directory uses — `ON CONFLICT DO UPDATE` on the composite key, `DISTINCT ON` for
the newest row per source, a `GROUP BY` for the counts — and the contract suite
is parameterised over both backends, so the row exists and is waiting for a
database rather than being absent.

**`tests/contract/console` is green: 270 passed, 4m23s.** Two of its tests
(`test_console_visual_regression.py` and
`test_console_gate.py::test_a_seeded_end_to_end_failure_fails_the_gate`) failed
on first contact for want of a Playwright browser and a standalone build — a
provisioning gap in this worktree, confirmed pre-existing by stashing the whole
branch and running them against master. After
`pnpm exec playwright install chromium-headless-shell` and `make console-build`
they pass.

A third failed for a reason that *was* this branch's doing, and §18 records it.
It is worth saying here why this section originally claimed green without it:
the suite run quoted above was `pytest tests/ --ignore=tests/contract/console`,
and excluding a directory because two of its tests need a browser meant not
running the two hundred and sixty-eight in it that do not. That is the whole
mechanism of the miss.

<!-- defer: theme=live-cluster-validation -->

---

## 17. What the done-audit found

Run against the whole branch diff. It confirmed all seven Definition-of-done
items met against tests that assert behaviour rather than fixture construction;
confirmed each of the six handoff ids was one this feature was actually given,
and each either closed with real work (§6, §7, §8 — it checked the diff for each
rather than taking the prose) or re-deferred with a fresh mark (§14); confirmed
no gate configuration was loosened and no `skip`, `xfail` or weakened assertion
was added anywhere in the diff; confirmed no pre-existing test was edited to
mean something weaker — the two it looked at, `test_tenant_isolation.py` and
`test_port_conformance.py`, are strictly additive; and confirmed the one test
that could plausibly have read the wall clock,
`test_a_re_notification_outside_the_retry_window_links_rather_than_repeats`,
drives a stub clock instead.

It also read item 7 the way §9 asks it to be read: met for the transit half, and
honestly scoped rather than quietly narrowed for the rest.

**It found one thing, and it was a real regression this branch introduced.**
§18 records it, and it is recorded as a finding rather than folded silently into
the work, because the interesting part is not the fix.

---

## 18. A gate this branch broke, and the exclusion that hid it

**Found by the audit, not by me, and worth saying in those terms.**

`tests/contract/console/test_console_shell.py::test_the_fixture_server_answers_endpoints_the_dataset_actually_has`
failed deterministically, in half a second, with no browser or build involved:

```
AssertionError: /v1/transit/simulate is not a read the dataset covers
```

**What broke it.** §12's fixture wiring added `/v1/transit/simulate` and
`/v1/transit/deliveries/{delivery_id}/resend` to the fixture server's
`SHELL_ENDPOINTS` table, so the browser suite could exercise the simulation and
the re-send. Both are `POST`. The test holds that table against the mock plane's
catalogue *filtered to `GET`*, with one hard-coded exemption for the
configuration preview — the one write the capture already answered.

**Why it went unseen.** The suite run in §16 was
`pytest tests/ --ignore=tests/contract/console`. Two tests in that directory
needed a browser this worktree was provisioned without, so the whole directory
was excluded — and with it the two hundred and sixty-eight tests that needed
nothing. Excluding a directory to skip two tests is how a deterministic failure
in it becomes invisible, and the honest lesson is that the exclusion was the
defect rather than the tests it was hiding.

**The fix, and why it is not a widened exemption.** The obvious repair was to
add two more literals beside `/v1/config/{node_id}/preview` and `continue`. That
would have been a list somebody appends to whenever a path fails this test,
which is the moment it stops being a check. Instead the test now builds a second
map from the catalogue's *non-`GET`* endpoints and matches a declared write path
against that — so an entry still has to name an endpoint the catalogue declares,
with the slug the catalogue gives it. The previously exempt configuration
preview is now checked too, which it was not before.

**Confirmed still able to fail.** A bogus `'/v1/no-such-endpoint': 'nonsense'`
seeded into the table fails with `is not an endpoint the dataset covers`;
removed, the suite is green. The whole directory now runs: **270 passed**.

<!-- proof: tests/contract/console/test_console_shell.py::test_the_fixture_server_answers_endpoints_the_dataset_actually_has -->

---

# Second dispatch — the three handoffs 061 addressed to this feature

The feature body above was finished and merged. This section records a later
dispatch that carried three new handoff marks from 061, each naming 062 as the
place the work belonged. They are recorded here rather than in a new document
because a handoff is answered where the feature that received it keeps its
record.

---

## 19. The scheduler could claim any job and run exactly one kind of them

**Handoff `9fe09d60`, from 061.** Give the scheduler a dispatcher keyed on job
kind, so `knowledge.sync`, `knowledge.corpus_sync` and `topology.discovery` run
rather than only being registerable.

**Done, and the gap was worse than "three kinds have no runner".** There was no
path at all from a claim to work of an arbitrary kind. `JobExecutor.execute`
takes a `Schedule`, which is the *investigation*-shaped reading of a stored job;
nothing else consumed a claim. So the three definitions were inert in the most
expensive way available: the row exists, the console shows it enabled, the store
says it is due, and a corpus quietly describes last quarter for ever.

**`platform/scheduler/dispatch.py`** is the missing piece — `JobKindDispatcher`
mapping kind to one runner, and `ScheduledJobWorker` claiming, reading the job,
dispatching and releasing.

**Three decisions worth the argument.**

*A kind with no runner fails; it does not pass and it does not hang.* Recording
it as a success would put a green run in the operator's history of a job that
did nothing — worse than the gap it covers. Releasing the claim anyway is what
stops a job nobody can run from also blocking its worker for a lease, every
lease, for ever.

*A second runner for one kind is refused rather than replacing the first.* Two
runners for one kind is the same work done twice a night or the wrong one of the
two doing it, and both are found months later.

*The job is read after the claim rather than carried on it.* `JobClaim` has no
`kind` field, and adding one meant either a migration on `job_claims` or a value
that `heartbeat` and `expire_leases` — which read the claim row alone — would
return empty. The claim already carries `org_id` and `job_id`, which is enough
to read the job inside the tenant's own unit of work. One lookup, and no second
copy of two fields that can disagree with the first.

**A failed run is rescheduled.** A sync that failed tonight still syncs
tomorrow: a failure is a bad run, not a deletion, and leaving it unscheduled
would turn one unreachable wiki into a job that stops for ever without saying so.

**`next_due` understands two vocabularies**, and that is not tidiness. The
scheduler owns cron, but `platform/estate/discovery/schedule.py` writes
`every 900s` from an integration's declared interval — because "every fifteen
minutes" is what an integration means and a cron expression would make eighty
integrations all sweep at `:00`. A dispatcher that answered "unparseable" to the
only other vocabulary in the tree would have unscheduled every sweep it ran.

<!-- handoff-done: id=9fe09d60 -->
<!-- proof: tests/unit/platform/scheduler/test_kind_dispatch.py::test_a_due_job_reaches_the_runner_its_kind_names -->
<!-- proof: tests/unit/platform/scheduler/test_kind_dispatch.py::test_a_kind_with_no_runner_fails_with_the_kind_named -->
<!-- proof: tests/unit/platform/scheduler/test_kind_dispatch.py::test_a_kind_with_no_runner_still_releases_its_claim -->
<!-- proof: tests/unit/platform/scheduler/test_kind_dispatch.py::test_a_second_runner_for_one_kind_is_refused -->
<!-- proof: tests/unit/platform/knowledge/base/test_sync_runners.py::test_the_corpus_pass_reads_for_the_team_its_payload_names -->
<!-- proof: tests/unit/platform/estate/test_discovery_runner.py::test_the_run_sweeps_the_source_the_payload_names -->

---

## 20. Every shipped kind is registered, including on a deployment that wired nothing

**Not in the handoff.** It says the three kinds should run. It does not say what
a deployment that has configured no wiki should see.

**Done.** `gateway/http/scheduled_work.py::dispatcher_for` registers all three
unconditionally, even when `knowledge_sources` is empty.

**Why not skip the registration.** The two messages are aimed at different
people. *"No runner is registered for kind `knowledge.sync`"* reads as a hole in
the build, and sends an operator to a maintainer. *"No sync source named 'wiki'
is configured; this deployment can sync: nothing"* reads as their own
configuration, which is what it is. Skipping registration would have produced
the first sentence for the second situation.

`GatewayState` gained `knowledge_sources` and `corpus_sources`, mirroring
`discovery_sources` exactly — empty until composition wires one, because a wiki
adapter needs a client and the client needs the credential proxy. The topology
runner needed no new field: `discovery_sources` was already there, which is why
`topology.discovery` is the one of the three that is genuinely runnable today on
a deployment that has onboarded an estate.

<!-- proof: tests/unit/gateway/http/test_scheduled_work.py::test_a_deployment_with_nothing_wired_names_the_source_not_the_kind -->
<!-- proof: tests/unit/gateway/http/test_scheduled_work.py::test_the_three_kinds_that_had_no_runner_now_have_one -->

---

## 21. The bridged catalogue was composed and unreachable

**Handoff `19ee16d0`, from 061.** Compose a bridged catalogue at the gateway and
serve it — an MCP server's tools with their origin, their classification and
their server's health — using the same per-source liveness, caching and timeout
policy 062 already needs for ingress state.

**Done.** `GET /v1/protocols/catalogue`, over
`capabilities/protocols/catalogue.py::bridged_catalogue`, which already composed
discovery, the classification table and the health probe. Nothing was missing
from the composition; what was missing was any way to reach it from outside the
process. An operator classifying `deploys.roll_out` had to already know the tool
existed.

**What a row carries, and why each part.** The qualified name (`server.tool`) is
what an operator classifies against; the catalogue name (`server__tool`) is what
the model calls and what a run's trace records. Both are served, because they are
deliberately different strings and something has to make them traceable to each
other. The declared side effect is carried and never acted on — an operator
should be able to *see* a server describing a write as a read.

**The three policies the handoff names, and where each one actually lives.**

*Liveness is per server*, and an unreachable one reports its reason where its
tools would be. A server that is down and a server that offers nothing produce
the same empty tool list, and only one of them is something anybody can fix. The
list is built from the team's own registrations rather than from what the
adapter answered, so a server registered and never reached still appears.

*Caching is here*, keyed per team, thirty seconds, expiring from when the entry
was written rather than when it was last read. An entry refreshed on every read
would keep an outage on the screen for exactly as long as somebody kept looking
at it — which is the period during which they are looking *because* of it. An
unreachable server is cached like any other answer: re-probing a down server on
every refresh turns one outage into a second one.

*The timeout is not here, and deliberately.* Each adapter already applies
`PROTOCOL_DISCOVERY_TIMEOUT_SECONDS` to its own discovery. A second timeout at
this layer would be a second thing to disagree with the first about what "did
not answer" means.

**No new permission.** `CONFIG_READ`: the registrations *are* configuration, and
anybody who may read a team's configuration can already read the list of servers
it declares. What this route adds is what those servers answered.

**A deployment with no adapter says so.** `protocol_adapter` is `None` until
composition wires one — reaching an MCP server needs a transport and the
credential proxy, the same posture `deep_verifier` and `discovery_sources` take.
The route then answers with the registrations, no servers, and a sentence, rather
than with an empty catalogue that an unwired bridge and a team with no tools
would both produce.

<!-- handoff-done: id=19ee16d0 -->
<!-- proof: tests/unit/gateway/http/test_protocol_catalogue_routes.py::test_a_bridged_tool_is_served_with_its_origin_and_its_classification -->
<!-- proof: tests/unit/gateway/http/test_protocol_catalogue_routes.py::test_a_server_that_did_not_answer_reports_why_instead_of_its_tools -->
<!-- proof: tests/unit/gateway/http/test_protocol_catalogue_routes.py::test_an_unclassified_tool_is_shown_and_is_not_executable -->
<!-- proof: tests/unit/gateway/http/test_protocol_catalogue_routes.py::test_a_second_read_inside_the_window_does_not_contact_the_server_again -->
<!-- proof: tests/unit/gateway/http/test_protocol_catalogue_routes.py::test_the_window_expires_so_a_server_coming_back_is_noticed -->

---

## 22. The ordered-list control needed the catalogue to describe an entry first

**Handoff `a0dcaee7`, from 061.** Build the configuration editor's control for an
ordered list of objects — 062's routing rules are the motivating case — then
apply it to `agents.subagents`, with click-through per specialist on the agent
screen and a topology template through preview-then-save.

**Done for the control and for the application to `agents.subagents`.** §23
records the two parts that are not, and re-defers them.

**The control could not be built where the handoff implies it could.** The
editor's own rule is that every control comes from the catalogue — "a console
holding its own table would offer values the write path refuses". But
`GET /v1/config/{node_id}/fields` described `transit.rules` as one field of type
`array` and stopped there. So a rules editor had exactly two options: hold a
client-side table of what a routing rule is made of, which is the thing that
rule forbids, or not exist, which is where it was.

**So the catalogue describes an entry now.** `ConfigField.item_fields`, walked by
the *same* walker that describes every other field, so a field added to
`RuleSettings` is a control on the same commit. Each item's path is relative to
the entry, because an entry nobody has added yet has no index and an absolute
path would name a row that does not exist.

`ItemFieldView` is a separate model from `ConfigFieldView` rather than a reuse:
half of that one is about a *node* — provenance, whether this node sets it, which
ancestor locked it — and none of it is true one level down. A list replaces
entirely, so an entry inherits the list's answer to all of it and has none of its
own.

**An array of scalars keeps no item fields**, and that is the line. There is
nothing inside a string to draw, and a row of controls for one would be a shape
the console invented. `capabilities.enabled` still reports "edited as a document
rather than here", which is what it is.

**Three properties in the control, each a way a list editor lies.**

*Order is the value.* Moving an entry changes what gets written, not just what is
drawn. Routing rules are first-match-wins with an explicit last word; specialists
are dispatched down the list. A row that could be moved but did not say where it
sat would be a set editor offered for something that is not a set, so each row
draws its position.

*The whole list travels.* A list replaces entirely — that is what the merge does
— so the patch carries every entry including the untouched ones. Sending only the
edited entry would silently delete the rest, and this is the shape of editor
where that is a plausible mistake rather than an unlikely one.

*The preview guarantee is not weakened by a bigger control.* Adding, removing and
reordering are edits like any other: each takes the save control away until the
deployment has been asked again.

**The pending list rides as JSON in the existing pending map** rather than as a
second kind of pending state. One shape of pending change means one
invalidates-the-preview comparison; two would eventually disagree about whether
a preview was current, and the disagreement would be silent.

**Reordering is two buttons rather than a drag.** A drag is unusable from a
keyboard without building a second interaction anyway, and the second interaction
is this one.

**One pre-existing fixture was corrected**, not weakened:
`config-editor.test.tsx`'s `field()` helper gained `itemFields: []`, which is
what a list of plain values is, and the test it feeds still asserts exactly what
it asserted before.

<!-- proof: tests/unit/platform/config_service/test_fields.py::test_a_list_of_objects_describes_the_fields_one_entry_has -->
<!-- proof: tests/unit/platform/config_service/test_fields.py::test_a_list_of_scalars_describes_no_entry_fields -->
<!-- proof: tests/unit/platform/config_service/test_fields.py::test_the_specialists_a_team_declares_are_an_ordered_list_of_objects_too -->
<!-- proof: console/tests/unit/surfaces/object-list.test.tsx -->

---

## 23. Two parts of `a0dcaee7` are re-deferred, and this is what is missing

**Not done: click-through per specialist on the agent screen.** The agent screen
today ends its specialists panel with one shared link to `/configuration`. Making
it per specialist needs a deep-link the configuration screen does not have —
there is no `?field=` or anchor plumbing on that screen at all, so the work is
reading a parameter on a server component, passing a focus down through
`ConfigEditor`, and having the list highlight one entry.

The version that could have been built quickly is the one worth refusing: an
anchor derived from an entry's `name` field. Which field identifies an entry is
not something the catalogue says, so the console would be guessing that a list of
objects has a field called `name` — and it would be right for specialists and
wrong for the next list somebody adds. That is the client-side schema §22 exists
to remove, reintroduced one level down.

**Not done: a topology template through preview-then-save.** The precedent is the
operating-context template — derived from the estate, offered as a starting
document, and empty once anything is written, "because a suggestion that kept
reappearing over an operator's own text is one they stop reading". A topology
template is the same shape for `agents.subagents` and needs the same two halves:
something that derives a starting set of specialists, and a surface that offers
it without applying it. Neither exists, and inventing a set of specialists to
have something to offer would be deciding what a team's topology should be from
inside a console.

Both are now cheaper than they were: the control they were to be attached to
exists, and an entry's shape is something the deployment describes.

**The mark this section was missing.** §22 and §23 together are the whole answer
to `a0dcaee7` — two of its four parts built, two re-deferred by name — but the
`handoff-done` mark that says so was never written, so the handoff stayed open
and the close refused. Recorded here rather than quietly added: the omission was
bookkeeping, not a second opinion about what was built, and §14 already had the
shape this should have followed — a `handoff-done` for the original, immediately
followed by the new handoffs that carry what is left.

<!-- handoff-done: id=a0dcaee7 -->
<!-- handoff: to=063-config-deep-links what="give the configuration screen a deep link to one field and one entry of an ordered list, and use it for the per-specialist click-through on the agent screen — the entry's identity has to come from the catalogue rather than from the console guessing that a list has a field called name" -->
<!-- handoff: to=063-topology-template what="derive a starting set of specialists from what the deployment already knows, and offer it as a topology template through preview-then-save, in the shape the operating-context template already has — offered, never applied, and gone once anything is written" -->

---

## 24. Test-first, and where it was confirmed

`9fe09d60`: red on `ModuleNotFoundError` for `platform.scheduler.dispatch`, then
one red assertion after the module landed (a rescheduled job is not due five
minutes later, which was the test's premise being wrong rather than the code's).

`a0dcaee7`: five red in the field catalogue, twelve red in the console suite,
each confirmed before anything was written.

`19ee16d0` is the honest exception. The suite was written before the route
existed and would have failed on the import, but it was not *run* red — the
first run was after the implementation, and nine passed. So the bite was
confirmed the other way, the way §18 confirmed its own: two regressions were
seeded into the route (an unreachable server's detail dropped, and
`awaiting_classification` hard-coded to `False`) and the two tests that should
have caught them did, deterministically. Recorded rather than glossed, because
"I wrote the test first" and "I watched it fail" are different claims.

---

## 25. Gate for this dispatch

```
make lint format-check typecheck check-imports check-constants   all pass
make check-protocols                                             passes
make console-lint console-typecheck                              pass
uv run pytest tests/unit/platform/scheduler                       66 passed
uv run pytest tests/unit/platform/knowledge tests/unit/platform/estate
                                                                354 passed
uv run pytest tests/unit/gateway                                526 passed
uv run pytest tests/contract (bar tests/contract/console)      4842 passed
uv run pytest tests/unit/platform/config_service               332 passed
uv run pytest tests/unit/tools tests/contract/fixtures          547 passed
console unit suite                                             1591 passed
```

`fixtures/contract/openapi.json` was regenerated with
`python -m tools.mockplane contract` and `console/src/api/schema.ts` with
`pnpm run client`: both the new route and `item_fields` change the document, and
`test_the_committed_document_is_what_the_application_generates` failed until
they were. That test is the reason the drift was found at all rather than by a
screen.

`make test-postgres` was not run and this dispatch touches no migration and no
repository — the persistence change in the feature body remains the one §16
records as waiting for a database.

---

## 26. The console gate caught two things §25 had claimed were green

**Found by `tests/contract/console/test_console_gate.py`, not by me**, and worth
recording in those terms because §16 and §18 record the same lesson: running a
subset and calling it the gate is how a deterministic failure stays invisible.
`make console-lint console-typecheck` and the vitest suite all passed. The two
checks I had not run were `format-check` and `test` — and `test` is not the
vitest suite, it is the vitest suite *with the coverage floor*.

**`format-check`.** `preview.tsx` and `object-list.test.tsx` were not
Prettier-formatted. Mechanical, fixed by formatting them.

**`test`, and this one is the interesting one.** Branch coverage fell from
90.14% to **89.81%**, against a floor of 90. The ordered-list control is a lot
of new branching — a type per item control, a default per item type, the ends of
the order, a value that is not the shape the schema declares — and the suite
exercised the paths an operator takes rather than all of them.

**Fixed by covering the branches, never by touching the floor.** The tests added
are behaviours worth asserting on their own, which is the only honest way to do
this:

- a switched-off entry is written as a **boolean**, and a numeric field as a
  **number**. Both matter: `"true"` and `"8"` are refused by the write path, and
  refused *after* the operator has previewed and pressed save — the worst moment
  to find out a control was lying about what it produced;
- a new entry starts at each field's own declared default, and a boolean with no
  declared default starts switched off rather than absent;
- a stored value that is not a list, and an entry that is not an object, cost the
  operator that one field rather than the screen they were going to fix it from.
  This control is rendered inside the form for a whole node;
- the first entry cannot move earlier and the last cannot move later;
- nothing in the list is editable while its override is being cleared.

Plus `console/tests/unit/surfaces/editable.test.ts`, which was missing entirely:
`editableFields` had no direct test at all, and it is the module whose whole
claim is that it invents nothing.

**Where it landed: 90.11%, against a floor of 90.** Said plainly rather than
rounded up — that is a thinner margin than the 90.14% this branch started from,
and the next feature to add a branchy control will meet the floor before it
meets a reviewer. The remaining uncovered branches in `preview.tsx` are
defensive paths unreachable through the interface: the guard inside `move`
(both buttons are disabled at the ends, so it cannot be reached by clicking) and
`safeParse`'s `catch` (the only writer of that string is `JSON.stringify` two
lines away). Both are worth keeping — this control renders inside a whole
node's form, and a throw there costs the screen — and neither can be exercised
without a test that lies about how it was reached.

<!-- proof: console/tests/unit/surfaces/editable.test.ts -->
<!-- proof: console/tests/unit/surfaces/object-list.test.tsx -->

---

## 27. Nothing calls the worker on a timer, and that was true before this dispatch

**Found by the done-audit.** `gateway/http/scheduled_work.py::worker_for` builds
a `ScheduledJobWorker` and nothing invokes `tick()` on a schedule. So the three
kinds are dispatchable and are not yet *dispatched* by a running process.

**Recorded rather than quietly fixed, because the boundary is real.** The
handoff asks for a dispatcher keyed on job kind so the three kinds run rather
than only being registerable, and the gap it names is the claim→runner link,
which did not exist and now does. What still does not exist is a loop in the
gateway process that claims on an interval — and that was equally true of the
investigation path before this branch: `JobExecutor` has never been driven from
a timer here either. Adding one would be introducing this deployment's first
background scheduler loop, its shutdown behaviour and its interval, on the way
past a handoff about dispatch.

<!-- handoff: to=063-scheduler-loop what="drive ScheduledJobWorker.tick on an interval in the gateway process, with the drain behaviour graceful shutdown already has for background runs — the dispatcher and every runner exist and nothing claims on a timer, which is equally true of the investigation path that predates them" -->
