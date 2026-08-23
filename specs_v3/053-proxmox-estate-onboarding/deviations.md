# Deviations — 053 The Proxmox cluster as the first estate

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. `SDN.Audit` is declared and advisory, not required

**Planned.** T-001: "`READ_PRIVILEGES` includes `SDN.Audit` on `/` and
`Sys.Syslog` on `/`, each with `capabilities` naming what it unlocks; the
declaration consistency check covers the additions."

**Done.** `Sys.Syslog` on `/` went into `READ_PRIVILEGES` naming
`proxmox_corosync_links`, which is the capability that reads `/cluster/log` and
is genuinely behind that privilege. `SDN.Audit` went into a new third tuple,
`ADVISORY_PRIVILEGES`, and `PrivilegeReport` gained `missing_advisory` and
`advisory_sufficient` beside the read and write halves.

**Why.** `READ_PRIVILEGES` is what `read_sufficient` is computed from, so a
privilege in it is a privilege a missing grant *refuses the wizard over*. No
shipped capability reads any SDN endpoint — zones in this feature come from the
declared inventory, which is what the specification's own §B says they come
from — so requiring it would tell an operator whose token reads their entire
cluster that their credential is insufficient, and the fix they would reach for
is a wider grant. That is the exact failure mode the module's docstring already
argues against for the write privileges.

The specification's justification names only syslog: "a token that cannot read
`syslog` produces an investigation that does not find the cause". It lists
`SDN.Audit` in the role to create and says nothing about what breaks without it,
which is consistent with what the code shows: nothing does, yet.

The consistency check is asserted in both directions.
`test_every_required_privilege_names_a_capability_this_integration_declares`
holds that every `READ_PRIVILEGE` names a capability the catalogue reports for
this integration, and
`test_an_advisory_privilege_names_no_capability_and_says_why` holds that an
advisory one names none — so the day a capability starts reading SDN, moving it
into `READ_PRIVILEGES` is a decision somebody takes rather than a drift nobody
notices.

<!-- proof: tests/unit/integrations/test_proxmox_privileges.py::test_the_advisory_privileges_name_sdn_audit_and_refuse_nothing -->
<!-- proof: tests/unit/integrations/test_proxmox_privileges.py::test_every_required_privilege_names_a_capability_this_integration_declares -->
<!-- proof: tests/unit/integrations/test_proxmox_privileges.py::test_a_token_that_cannot_read_the_cluster_log_is_named_not_summarised -->

---

## 2. Enrichment matches on the correlation key, and the plan says which kinds it speaks for

**Not in the plan.** `plan.md` §C says annotations are "matched by VMID".

**Done.** `Annotation.correlation_key`, matched against
`Resource.correlation_key`, which for a Proxmox guest is `{cluster}/{kind}/{vmid}`
and for a node is the node's own name. `integrations/proxmox/enrichment.py::guest_key`
is the one expression that spells it, and the discovery source's
`correlation_key` is the same one.

**Why it could not be the native identifier.** Identity is derived from the
provider's name *plus a creation-time discriminator*, precisely so a reused VMID
does not inherit a dead guest's history (feature 038, deviation 6). A guest's
`native_id` is therefore `lxc/HAL9000/<created>/100`, which is deliberately not
something a hand-maintained file can spell. The correlation key is the value
both sides chose, which is what it exists for.

**And a second half the first sweep at size found.** `EnrichmentPlan.kinds`
names the kinds the five documents speak about — node, container, virtual
machine. Without it, every physical disk and thin pool in the estate came back
as `only_in_provider`, because a disk has a correlation key (its serial) and no
inventory entry. Seventeen genuine findings were buried under fifty that were
not findings at all.

<!-- proof: tests/unit/integrations/test_proxmox_estate_onboarding.py::test_the_container_only_the_cluster_knows_about_is_a_finding_too -->

---

## 3. An address and a domain are structural attributes, and are no longer masked

**Not in the plan.** `plan.md` §C says the ingestion screens every string
through `platform.estate.attributes.screened`, "which already exists for exactly
this".

**Done.** It does — and `screened` gained `STRUCTURAL_ATTRIBUTES`, a named set
(`address`, `domain`) whose values are still passed through the guardrail
ruleset for secrets and are **not** passed through the masking policy.

**Why it had to change.** The default masking policy turns `10.20.20.10` into
`NSRE_MASK_IP_1` and `dmz-01.example.internal` into `NSRE_MASK_HOST_1`. Both are
correct behaviour for a prompt leaving the deployment and both are fatal here:
the zone is *derived from* the stored address, so a masked one places every
resource in the estate nowhere, and a masked domain cannot be resolved to the
container that serves it. Acceptance 3 and acceptance 6 are both unreachable
with masking applied to those two fields.

This is an extension of a line feature 038 already drew rather than a new one.
Its deviation 10 exempts kind, source, native identifier, display name and
parent from screening, for the reason that "an operator looking for `pve1` has
to be able to find `pve1`". An address is that argument twice: it is how a
machine is found and it is what its zone is derived from. Secret redaction is
unaffected, so a field carrying a token is still redacted before storage.

The exemption is two names in one constant with the reasoning beside it, so
widening it is a visible change rather than a habit.

<!-- proof: tests/unit/integrations/test_proxmox_estate_onboarding.py::test_the_per_zone_counts_match_the_declared_inventory -->
<!-- proof: tests/unit/integrations/test_proxmox_estate_onboarding.py::test_a_service_domain_resolves_to_the_container_that_serves_it -->

---

## 4. The divergence report needed a column, so the sweep record gained one

**Planned.** T-010: "the divergence report is stored with the sweep report and
served".

**Done.** `SweepRecord.findings`, a JSONB column on
`estate_discovery_sweeps`, migration `0009_sweep_findings`, written by the
enrichment post-step under one key (`FINDINGS_ENRICHMENT`) and read back by
`GET /v1/estate/discovery/report`.

**Why on the sweep rather than on the resources.** Two of the three divergence
kinds are about a resource and could have been attributes; the third — an entry
the file declares and the provider does not report — has no resource to hang
off, and it is the one the specification calls out by name: "a resource present
only in the file is a resource that no longer exists, and that is also a
finding". Storing two kinds on resources and the third somewhere else would have
made "what did last night's sweep disagree about" a question with two answers.

Nullable rather than defaulting to `{}`: a sweep recorded before this column
existed concluded nothing extra, and an empty object would claim it had looked.

<!-- proof: tests/unit/integrations/test_proxmox_estate_onboarding.py::test_the_divergence_report_is_kept_with_the_sweep_that_found_it -->

---

## 5. The deep verify and the discovery source are composition, not construction

**Planned.** `plan.md` §A: `POST /v1/integrations/{name}/verify/report` "runs
the integration's own verifier"; §A.3: `POST /v1/estate/discovery/preview` "runs
`ProxmoxDiscovery.discover`".

**Done.** Both, through two new fields on `GatewayState` —
`deep_verifier: DeepVerifier | None` and
`discovery_sources: Mapping[str, ResourceReader]` — that a composition root
supplies and that default to nothing.

**Why.** The gateway has no vendor transport and cannot build one: reaching a
Proxmox node means a `ProxyTransport` over the credential proxy, and
`gateway/http/asgi.py` composes a persistence gateway and a token service and
nothing else. A route that constructed a client from ambient configuration would
be reaching a cluster nobody chose, which is the argument `GatewayState` already
makes in as many words for `model_verifier` and for the investigator.

So the shape is the one this repository already holds for exactly this problem:
composed or absent, and absent refuses with a sentence naming what is missing
rather than answering with an empty document. An empty privilege report reads as
a clean bill of health, which is the worst of the three possible answers.

<!-- proof: tests/unit/gateway/http/test_estate_onboarding_routes.py::test_a_deployment_that_composed_no_deep_verifier_says_so -->
<!-- proof: tests/unit/gateway/http/test_estate_onboarding_routes.py::test_previewing_an_integration_nothing_is_pointed_at_names_the_next_step -->

---

## 6. Confirming the preview is `POST /v1/estate/discovery/sources`, not a parameter

**Planned.** T-005: "implement the confirmation route or parameter".

**Done.** A route of its own, which writes the recurring sweep job through
`sweep_job` into the schedule store the scheduler already claims from. The job
identifier is derived from the source, so confirming twice updates the schedule
rather than sweeping the cluster twice as often, and it is due immediately
rather than after the declared interval.

**Why a route.** A flag on the preview would make "look" and "commit" one
request, and the whole argument for the preview existing is that they are two
decisions with a person in between. Due immediately because an operator who has
just confirmed expects the estate to fill, and five minutes of an empty screen
is indistinguishable from a broken one.

<!-- proof: tests/unit/gateway/http/test_estate_onboarding_routes.py::test_confirming_registers_the_sweep_the_scheduler_claims -->
<!-- proof: tests/unit/gateway/http/test_estate_onboarding_routes.py::test_confirming_twice_leaves_one_sweep_rather_than_two -->

---

## 7. Ingestion is path-only in this build, and URL is the seam rather than a code path

**Planned.** `plan.md` §C: "the ingestion transport is path-or-URL, read-only,
no `./infra` execution".

**Done.** `InventoryReader`, a one-method protocol (`read(name) -> bytes | None`),
with `DirectoryInventory` as the shipped implementation. A deployment that
fetches the five documents over HTTPS composes a reader that does; nothing in
the ingestion changes.

**Why not both today.** An HTTPS fetch from tier 2 is an outbound call, and
every outbound call in this repository goes through the credential proxy — which
this one has no credential for and no host allow-list entry for. Writing it
would have meant either a second, unproxied egress path or a proxy rule for a
host nobody has configured, and neither could be honestly tested here. The seam
costs one protocol and makes the decision a composition one.

Only `inventory/cluster/*.yaml` is read and nothing in the tree is executed,
which is the part of the requirement that was load-bearing.

<!-- proof: tests/unit/integrations/test_proxmox_inventory_ingestion.py::test_a_reader_pointed_at_nothing_says_so_rather_than_ingesting_an_empty_estate -->

---

## 8. The JSON Schema validator is a declared subset, guarded by a test

**Planned.** T-007: "validates against bundled copies of their JSON Schemas".

**Done.** Five schemas under `integrations/proxmox/inventory_schemas/`, and a
validator in `integrations/proxmox/enrichment.py` implementing exactly the
keywords they use: `type`, `required`, `properties`, `additionalProperties`,
`items`, `enum`, `minimum`.

**Why not a library.** `jsonschema` is not a dependency, and adding one goes
through `tools/check_dependencies.py` and the constitution's Article X — a
dependency decision that a feature about a hypervisor should not be taking on
the way past.

**What makes the subset safe rather than convenient.**
`test_no_bundled_schema_uses_a_keyword_the_validator_ignores` walks every
bundled schema and fails on any keyword outside `SUPPORTED_KEYWORDS`. A subset
validator's danger is that it silently checks *less* than the schema claims; the
test converts that into a build failure at the moment somebody writes the
keyword rather than at the moment a bad document passes.

The schemas themselves are written here rather than copied: the repository they
model is not on this machine (see §12), so they are this feature's honest
reading of the five documents' shape, and they are the contract the ingestion
enforces either way.

<!-- proof: tests/unit/integrations/test_proxmox_inventory_ingestion.py::test_no_bundled_schema_uses_a_keyword_the_validator_ignores -->
<!-- proof: tests/unit/integrations/test_proxmox_inventory_ingestion.py::test_a_document_the_schema_rejects_names_every_problem_at_once -->

---

## 9. Enrichment reads one page, and says so when the estate is larger

**Not in the plan.**

**Done.** `apply_enrichment` queries with `limit=MAX_ESTATE_PAGE_SIZE` (500) and
sets `EnrichmentReport.truncated` when the page comes back full. The same bound
applies to the graph write.

**Why it is a limitation and not a bug.** `EstateQuery` has a `limit` and no
offset or cursor: the estate port cannot page. The default limit is fifty, which
is what the first run against the fifty-seven-container fixture actually hit —
forty resources annotated, seventeen declared entries reported as gone, and a
zone count of five. Raising it to the estate's own page bound fixes this cluster
and every cluster of its size, and leaves a real ceiling for a ten-thousand
resource estate.

`truncated` is what stops that ceiling being silent. An enrichment that quietly
covered the first five hundred of ten thousand would leave nine and a half
thousand resources looking as though nobody had declared anything about them,
which is the failure that looks exactly like a correct answer.

Paging the estate properly is a change to the repository port and both its
implementations, which is a feature rather than a paragraph.

<!-- handoff: to=062-data-ingress-and-delivery what="give EstateQuery a cursor so enrichment and any other whole-estate pass can page beyond MAX_ESTATE_PAGE_SIZE instead of reporting truncated" -->

---

## 10. The `address` attribute, and a fourth core kind field

**Not in the plan.** The plan assumes a resource's IP is available to derive a
zone from and does not say where it comes from.

**Done.** `guest_address` in `integrations/proxmox/discovery.py` reads the first
static IPv4 out of a guest's `netN` configuration lines, and `address` is a
declared attribute on the node, virtual-machine and container core kinds.

**Why from the configuration rather than from a running guest.** The address a
container was *given* is a fact about it whether or not it is up. Reading it
from the guest agent would make the zone disappear exactly when the guest
stopped — which is the moment somebody needs to know which zone the stopped
guest was in. `dhcp`, `manual` and IPv6 all return empty, and an empty address
becomes a `no_zone` divergence rather than an invented placement.

Declaring `address` on the kind is also what makes "which resources is a zone
expected of" answerable without a second list: a backup job declares no address,
so it is never reported as unplaced.

---

## 11. `NodeKind.ZONE`, and no new edge kind

**Not in the plan.** `plan.md` §D asks for "zone nodes and guest-to-zone
membership edges (a new use of an edge, existing `upsert_edge` machinery)".

**Done.** One new node kind, `ZONE`, and `EdgeKind.DEPENDS_ON` reused in both
new places.

**Why `DEPENDS_ON` rather than a membership edge.** The graph has exactly one
rule — an edge runs from the thing that would break to the thing whose failure
would break it — and both new edges obey it as they stand. A guest depends on
its zone: the zone's gateway failing takes every guest on that network with it,
so a zone's blast radius is its members, for free, through the traversal that
already exists. A service domain depends on the workload that serves it, which
is the edge feature 055 resolves a blackbox alert through.

A `MEMBER_OF` edge would have needed its own traversal to be useful, and blast
radius would not have seen it.

**Why a new node kind.** A zone is not something a sweep discovered — it is a
division somebody declared — and a traversal asking "what else is on this
network" must not have to filter `RESOURCE` nodes by an attribute.

<!-- proof: tests/unit/integrations/test_proxmox_estate_onboarding.py::test_a_zone_holds_the_guests_that_depend_on_it -->

---

## 12. The live cluster confirmation has not been run, and cannot be from here

**Planned.** Definition of done 2: "the same numbers confirmed once against the
live cluster, recorded in deviations." T-015: "run the real onboarding against
HAL9000 once."

**Not done, and this is the honest statement of why.** There is no cluster and
no repository on this machine. `/root/infra-cluster` does not exist, and nothing
in this checkout has an address or a token for a Proxmox node — the whole suite
is built on the recorded corpus precisely because of that, and
`test_no_proxmox_test_reaches_a_live_cluster` asserts it stays that way.

**What is proven instead, and what it is worth.** Every number the acceptance
criteria name is asserted against a fixture whose *declaration* is those numbers:
`tests/support/proxmox_estate.py` declares seven zones and the per-zone counts
(infra 25, apps 21, dmz 7, ci 2, backup 1, vk8s 1 — fifty-seven), and derives the
guests, their addresses, the cluster resource list, the fifty-seven guest
configurations and the five inventory documents from that declaration. So a test
asserting "infra holds 25" and a fixture producing 24 is not a thing that can
happen. What the fixture cannot prove is that the *real* cluster's guests are
laid out this way; that is the sentence this section exists to say plainly.

**The one arithmetic surprise, recorded because it will come up again.** The
specification's own numbers do not sum: 25 + 21 + 7 + 2 + 1 is fifty-six, and it
says fifty-seven containers across seven zones while naming five. The fixture
resolves it by putting the fifty-seventh container in the `vk8s` zone and giving
`mgmt` the two hypervisor nodes and no guests — which makes seven zones occupied,
fifty-seven containers, and every named count exact. If the real cluster
disagrees, the fixture's `ZONE_GUESTS` is the one place to change.

<!-- handoff: to=055-alert-ingress-first-investigation what="run the onboarding against the live HAL9000 cluster and its infra-cluster repository once, and record the real per-zone counts against the fixture's declaration" -->

---

## 13. The estate wizard step replaces the handover, and only where there is something to point at

**Planned.** T-014: "console wizard step: endpoint + token → verify → privilege
report rendered with failures and effects → preview counts → confirm."

**Done.** `console/src/surfaces/first-run/estate.tsx`, reached through a courier
at `console/src/app/api/estate/route.ts`, replacing the handover that step used
to be — but *only* when the deployment has a configured integration in the
`cloud_control_plane` category. With none, the step is the handover it was.

**Why the endpoint and the token are not in this step.** They are already the
integrations step: the credential form is generated from the vendor's declared
`CredentialFieldSpec`s and written through the existing courier. A second
credential form here would be a second place a secret enters the console, and
052's deviation 1 is about how carefully that path was built.

**Why a courier and not a direct call.** The same reason every other write in
this console is one: the session credential is an HTTP-only, `SameSite=Strict`
cookie on the console's host and a browser will not send it to the API origin.

**Confirming is genuinely disabled until a preview has come back**, and the test
presses it to prove that no request is made — rather than asserting that a
control looks unavailable.

<!-- proof: console/tests/unit/surfaces/estate-step.test.tsx -->
<!-- proof: console/tests/unit/shell/estate-route.test.ts -->

---

## 14. Divergence on `/resources` is a marked row *and* a panel

**Planned.** T-010: "`/resources` marks divergent rows".

**Done.** Both. A row whose correlation key the last sweep reported as
`only_in_provider` carries "(not in the inventory)" beside its name; the
`only_in_file` entries get a panel of their own, rendered only when there are
any.

**Why the panel.** A marked row cannot express the finding the specification
cares most about. "This machine is gone and the file still believes in it" is
about something with no row to mark, and rendering it only as an absence would
mean rendering it nowhere.

`ResourceSummaryView` gained `correlation_key` so the console can match a
divergence subject to a row without a lookup per row.

---

## 15. Test-first, per module, and the two places it was not

Followed per module. The privileges suite was observed red on
`ImportError: ADVISORY_PRIVILEGES`; the enrichment suite on
`No module named 'platform.estate.enrichment'`; the ingestion suite on
`No module named 'integrations.proxmox.enrichment'`; the route suite on eight
failures across three routes that did not exist.

Two exceptions, recorded because the alternative is pretending:

**The estate fixture's end-to-end suite was written before the code it needed to
pass and failed for real reasons rather than for import ones** — eight
assertions, and every one of them was a genuine defect the smaller tests could
not have found: the page limit in §9, the kind scoping in §2, the masking in §3.
That is the sequencing working.

**The console step's component tests were written after the component.** The
props are determined by the shape of three route responses, and writing the
tests first would have meant writing them against a guess. This is the same
admission 052's deviation 7 makes about the same screen, for the same reason.
Eight assertions, all passing on their first run, so they are established as
regression tests and not as specifications of behaviour that did not yet exist.

---

## 16. Answering the handoff this feature was given

052 handed this feature one obligation: "run the first-day browser project
against the compose backing and the validation container once a real estate
exists to finish the flow against." Three halves, and they came out differently.

**The browser project was run, and it is green.** Five tests, five passing,
against the `first-run` scenario:

```
uv run python -m tools.console_e2e run --project first-day --scenario first-run
5 passed (4.5s)
```

Worth recording that the first attempt was run without `--scenario first-run`
and three of the five failed — the runner defaults to `populated`, and the whole
point of that project is the empty deployment. The gate passes the scenario; a
person running it by hand has to.

**The compose backing could not be brought up here, and the reason is the
environment rather than the stack.** `deploy/compose/postgres.Dockerfile` builds
Apache AGE from source, and the build container cannot reach GitHub's release
CDN: `curl: (35) Recv failure: Connection reset by peer`, twice, on a clean
retry. The same URL answers `302` from the host, so this is docker's build
network and not the Dockerfile. `tools/console_e2e` reported it as what it is —
"the compose stack did not come up" — rather than as a test failure, which is
the harness behaving correctly.

**The validation container does not exist.** 051's own deviations say so in as
many words: "there is none in this checkout". There was nothing to run against,
so this half is not deferred so much as void until somebody builds one.

**And the premise — "once a real estate exists" — is not met either.** There is
no Proxmox cluster reachable from here; see §12.

So the mark is closed on the half that could be done and the rest is re-deferred
with what was learnt, rather than left open against a machine that cannot do it.

<!-- handoff-done: id=61ccc0f2 -->
<!-- handoff: to=055-alert-ingress-first-investigation what="run the first-day browser project against the compose backing on a machine whose docker build network can reach the Apache AGE release, and against a validation container once one exists" -->

See §17 for the rest of what was run.

---

## 17. Gate

Recorded as it was run.

- `make lint format-check typecheck check-imports check-constants` — green.
  Mypy strict over 1,668 first-party files, all seven import contracts.
- `uv run pytest tests/unit tests/contract` — green.
- The console gate's Python-side pieces: `make console-format-check`,
  `console-lint`, `console-typecheck`, `console-test` — green, with branch
  coverage back above the 90% floor after the courier and step tests landed.
- `fixtures/contract/openapi.json` and `console/src/api/schema.ts` regenerated,
  because three routes were added.
- The console gate end to end: lockfile, format, lint, types, unit tests with
  coverage, production build, generated client, budgets, both browser projects
  (`behaviour` 60 passed, `first-day` 5 passed), and the 20 visual baselines —
  all green, and **no baseline needed re-capturing**. The divergence panel on
  `/resources` renders only when the last sweep found one, and the mock plane's
  estate agrees with its inventory, so the screenshot is unchanged. That is the
  panel behaving as designed rather than the check being weak: the marked-row
  and departed-panel paths are held by the unit suite.
- `make test-postgres` — **green**: 471 passed, 15 skipped, 4m33s, against a
  real PostgreSQL. This is the gate 038's deviation 0 records being skipped on
  a machine that could have run it, so it was run here rather than named as
  somebody else's problem. It includes
  `test_migrations_roll_forward_and_back_over_seeded_data`, which takes
  `0009_sweep_findings` up and down over seeded data, and
  `test_scale.py::test_a_ten_thousand_resource_summary_answers_within_budget`,
  which is the suite that would notice the estate columns getting more expensive.

## 18. What the done-audit found

Run once, near the end, against this diff and this record. It confirmed the six
Definition-of-done items and the seventeen deviations above, checked that every
`proof` mark names a test that exists and asserts the claimed behaviour, and
mutation-checked the zone derivation — forcing `ZoneMap.zone_for` to return the
empty string fails five tests with real assertion errors rather than passing
quietly, which is what separates these from tests that would pass either way.

It raised one thing, and it was right: T-015 asks for `make test-postgres` green
and this record had it as an unrun gate named for the close step. It has now
been run — see §17 — because Docker is available on this machine, which is
precisely the reasoning 038's deviation 0 exists to refuse.
