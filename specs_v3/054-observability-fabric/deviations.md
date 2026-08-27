# Deviations — 054 Connecting the signals

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## Where each acceptance criterion is proven

| Criterion | Where it is proven |
|---|---|
| 1 — the six verify against real addresses and each returns data from a recent window, not merely 200 | `tests/contract/integrations/test_signal_sources_hold_recent_data.py::test_a_source_holding_records_verifies_with_the_count` and `::test_a_store_that_should_hold_something_and_does_not_fails_verification`, per vendor. Against the *real* addresses: not run — see §11 |
| 2 — an LXC pressure query provably uses host metrics by VMID and provably not in-guest metrics | `tests/unit/integrations/test_prometheus_resource_pressure.py::TestAContainersPressureQuery::test_every_selector_names_the_guests_own_identifier` and `::test_no_selector_names_a_metric_collected_inside_the_guest`, with the consequence measured in `tests/synthetic/test_signal_map_value_scenario.py::test_the_two_arms_reach_opposite_conclusions_from_one_recording` |
| 3 — every estate resource resolves at least one "up" source and one "logs" source, or names the missing integration | `tests/unit/platform/estate/test_signal_map.py::test_every_resource_answers_or_names_up_and_logs` and `::test_with_nothing_configured_up_and_logs_are_named_gaps_rather_than_silence` and `tests/unit/gateway/http/test_resource_signals.py::test_up_and_logs_both_resolve_for_a_watched_resource` / `::test_a_question_nothing_answers_names_what_would` |
| 4 — a source whose clock is off beyond tolerance verifies as degraded with the measured offset | `tests/unit/integrations/test_signal_source_verification.py::TestAClockOutsideTheTolerance` and, at the surface, `tests/unit/gateway/http/test_signal_source_verify_report.py::test_a_skewed_source_reaches_the_caller_as_degraded_with_the_offset` |
| 5 — Gatus and NetBox appear as known gaps with written reasons, in the catalogue response and on screen | `tests/unit/integrations/test_catalogue_gaps.py::test_the_two_observability_decisions_are_recorded_rather_than_forgotten`, `tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py::test_gatus_and_netbox_are_recorded_gaps_with_their_reasons`, and `console/tests/unit/surfaces/behaviour.test.tsx` → "is told what the catalogue does not cover, and why" |

---

## 1. An empty window is not always a finding, and the probe says which

**Planned.** `plan.md` §C: "**`DataWindowProbe`**: an authenticated read over a
recent window … that must return at least one series/line. 200-with-empty is
reported as its own state — `EMPTY_WINDOW` …".

**Done.** That, plus `EmptyWindow.BROKEN` / `EmptyWindow.EXPECTED` declared per
vendor, and `DataWindowOutcome.usable` reading the two differently.

**Why.** Two of the six answer empty as their ordinary state, and reporting
either as broken would train an operator to ignore the check on the day it
means something.

- **Alertmanager.** An alert router holding no alerts is an alert router doing
  its job. The probe still proves the query path and the parse; the *data* half
  has no failing case for this vendor and pretending otherwise would be the
  check crying wolf on every healthy deployment.
- **SigNoz.** A trace store for a cluster where nothing carries OTLP
  instrumentation is empty, and `spec.md` says so itself — SigNoz answers "what
  did it call" for *the instrumented CTs*, and today that set is empty.

The other four are `BROKEN`: a Prometheus with no series, a Loki with no lines,
an OpenObserve with no records and a Grafana with no dashboards are each exactly
as useful as being down and considerably harder to notice.

The distinction is data on the probe rather than a rule in the framework, so
adding a vendor means declaring what emptiness means for it rather than editing
a list somewhere else.

<!-- proof: tests/contract/integrations/test_signal_sources_hold_recent_data.py::test_a_source_whose_ordinary_state_is_empty_is_not_reported_as_broken -->
<!-- proof: tests/unit/integrations/test_signal_source_verification.py::test_an_expected_empty_window_says_why_empty_is_not_a_finding_here -->

---

## 2. Two of the six have no windowed read, and the probe says that too

**Planned.** `tasks.md` T-001 speaks of "an authenticated windowed read" for all
six.

**Done.** Four are genuinely time-ranged — Prometheus (`/api/v1/query_range`),
Loki (`/loki/api/v1/query_range`), OpenObserve (`/api/default/_search`) and
SigNoz (`/api/v3/query_range`) — and the request each sends carries the window's
own bounds, in the units that API indexes in. Two are not:

- **Alertmanager**'s `/api/v2/alerts` answers "what is firing *now*". It has no
  time range to ask for, and the client's own `list_incidents` deletes `start`
  and `end` for that reason.
- **Grafana** stores no time series at all. What it holds is dashboards, and a
  Grafana with none answers nothing this integration exists to answer.

**Why it is recorded rather than faked.** Both probes carry the window and do not
send it, and both descriptions say so in the sentence the report prints. The
alternative — inventing a filter the API does not have so that every probe looks
uniform — produces an empty result nobody can interpret, which is the exact
failure the family exists to prevent.

`DataWindow` therefore also carries milliseconds and microseconds beside
RFC-3339, nanoseconds and seconds: four APIs, four spellings of one instant, and
the one verifier that formats its own is the one whose empty result reads like an
empty store.

<!-- proof: tests/contract/integrations/test_signal_sources_hold_recent_data.py::test_a_windowed_read_asks_for_the_window_rather_than_all_of_history -->

---

## 3. The clock tolerance is thirty seconds and is *not* shared with Proxmox's

**Planned.** `plan.md` §C: "Same rationale as the Proxmox `clock_skew` tool
documents; the tolerance constant is shared."

**Done.** `config/constants/signals.py::SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS =
30.0`, beside and independent of
`integrations/proxmox/investigation.py::CLOCK_SKEW_TOLERANCE_SECONDS = 1.0`.

**Why sharing would have been wrong.** The Proxmox number is one second because
that is what corosync's token protocol tolerates between cluster members — it is
a fact about a consensus protocol, and it is far tighter than anything a human
would notice. Applying it to an HTTP signal source would report every one of the
six as degraded on the round-trip time alone.

The number here is about *correlation*: how far a source's clock may be from the
platform's before "the alert fired before the deploy" stops being a claim about
events and becomes a claim about two clocks. Thirty seconds still lines up on the
minute boundaries an investigation reasons in. Two different questions, two
constants, and each says in its own comment which question it answers.

<!-- proof: tests/unit/integrations/test_signal_source_verification.py::test_a_clock_inside_the_tolerance_verifies_with_the_measured_offset -->

---

## 4. The clock is read from the `Date` header, and an unmeasured clock is never an agreeing one

**Not in the plan.** `plan.md` says "from response headers or the vendor's status
endpoint" without choosing.

**Done.** `client_clock_probe` reads the `Date` header off the same connectivity
call the verifier already makes. No vendor gains a second round trip, and every
one of the six is covered without six different status-endpoint parsers.

**The half worth stating.** A source that sends no `Date` reports
`SkewState.UNREPORTED`, and `UNREPORTED` is explicitly *not* degraded and
explicitly not zero. A probe that reported an unmeasured clock as agreeing would
be the empty-window failure committed by the check built to catch it.

<!-- proof: tests/unit/integrations/test_signal_source_verification.py::test_an_unmeasured_clock_is_reported_as_unmeasured_not_as_agreeing -->

---

## 5. `SignalSourceVerifier` is a second protocol, not two more methods on the first

**Not in the plan.** `plan.md` says the probes "extend the existing
`probes()`/report shape".

**Done.** A separate `runtime_checkable` protocol. `VerificationRunner` checks
`isinstance` and runs the two probes only for a verifier that declares them;
`VerificationReport.data_window` and `.clock` are `None` for everything else, and
`to_record()` omits the keys entirely rather than writing nulls.

**Why.** `IntegrationVerifier` is implemented by around ninety verifiers. Widening
it would either break all of them or acquire defaults — and the only available
default for "did the clock agree" is a lie. The absent key is what lets a reader
tell "this was not measured" from "this measured nothing", which is the same
distinction the whole feature is about.

A contract test holds the set in both directions: the six declare it, and nothing
else does.

<!-- proof: tests/contract/integrations/test_signal_sources_hold_recent_data.py::test_nothing_outside_the_six_quietly_became_a_signal_source -->
<!-- proof: tests/unit/integrations/test_signal_source_verification.py::test_the_record_carries_the_new_probes_only_when_they_ran -->

---

## 6. Two assertions in the shared parity suite were changed, and neither was weakened

**Not planned.** `plan.md`'s blast radius says only "the parity suite must stay
green".

**Done.** Two tests in
`tests/contract/integrations/test_verification_names_what_is_missing.py` now
assert something different, because what they asserted stopped being what they
were named for.

**`test_a_working_credential_verifies_with_every_permission_granted`** asserted
`report.ok`. The suite's stand-in vendor answers `{}` to everything — which, for
a signal source, *is* an empty store, correctly reported. The test is named for
permissions and now asserts connectivity plus every permission granted, with a
docstring saying where the data half is asserted instead.

**`test_one_command_verifies_the_whole_catalogue`** asserted the summary line was
"N integration(s) verified". It now asserts that nothing may fail for any reason
other than an empty store — `report.data_window.is_finding` for every failing
entry — which is a *stronger* claim than the one it replaced, and one that fails
loudly if a signal source ever fails for a different reason.

Neither change loosens a gate. The first narrows a test to the property it is
named for; the second replaces a fixed string with a check on the cause.

---

## 7. `vmid` is a declared attribute on the two guest kinds

**Not in the plan.** `plan.md` §B says the map entry "carries the key (`vmid`)"
without saying where the value comes from.

**Done.** `platform/estate/kinds.py` declares `vmid: INTEGER` on `KIND_CONTAINER`
and `KIND_VIRTUAL_MACHINE`, and `integrations/proxmox/discovery.py` emits it.

**Why not the correlation key.** A guest's correlation key is
`{cluster}/{kind}/{vmid}`, so the number *is* recoverable by splitting a string —
and that is precisely the failure mode this feature exists to prevent. A selector
built from a parsed identifier returns nothing the day the format changes, and
nothing is exactly what a container under no pressure looks like. `typed()`
reduces raw attributes to the ones a kind declares, so an undeclared `vmid` would
have been silently dropped anyway.

This is the same line feature 053 drew for `address`, for the same reason: it is
what the answer is keyed by, so it is a structural fact rather than a decoration.

**What it means for an existing estate.** A resource swept before this change
carries no `vmid`, and the map resolves its *pressure* question to an explicit
gap naming what is missing rather than to a query with an empty selector. A
re-sweep fills it in.

<!-- proof: tests/unit/integrations/test_proxmox_discovery.py::test_every_guest_carries_the_identifier_its_host_side_series_are_keyed_by -->
<!-- proof: tests/unit/platform/estate/test_signal_map.py::test_pressure_for_a_guest_with_no_identifier_is_a_named_gap -->

---

## 8. "Is it up" is not a rule in the table

**Planned.** `spec.md` §B: "is it up? → Proxmox (guest state), Gatus
(synthetic)".

**Done.** The *up* question resolves against `resource.source` — whichever
integration discovered the resource — rather than against a rule naming Proxmox.

**Why.** Acceptance 3 asks that **every** estate resource resolve an "up" source.
A rule that named Proxmox would answer for a Proxmox estate and leave every
future provider's resources with a gap that is not a gap: the integration that
discovered a thing is the one that reports its state, and that is true whatever
it happens to be. Writing it as a property of the resource makes the criterion
hold by construction instead of by the rule table happening to be complete.

Gatus is the synthetic second source and is not built — see §10.

<!-- proof: tests/unit/platform/estate/test_signal_map.py::test_up_is_answered_by_whatever_declares_the_resource_exists -->
<!-- proof: tests/unit/platform/estate/test_signal_map.py::test_every_resource_answers_or_names_up_and_logs -->
<!-- proof: tests/unit/platform/estate/test_signal_map.py::test_with_nothing_configured_up_and_logs_are_named_gaps_rather_than_silence -->

---

## 9. The suggested endpoint is not prefilled into a form field, because there is no field

**Planned.** `plan.md` §A: "offered first, with the endpoint pre-filled from the
resource's primary IP and the integration's declared default port".

**Done, in two halves.** The **derivation** is complete: `GET /v1/integrations`
orders suggested entries first and carries
`suggested: {address, from_resource, because}` per entry, computed server-side by
`platform/estate/suggestions.py`. Both wizards render it — the console as a line
on the offer, the CLI as "found in your estate: prometheus
(http://10.20.20.37:9090)".

The **prefill** is not done, and cannot be. A self-hosted integration's
credential schema declares only the secret; the *endpoint* is not a credential
field at all — Prometheus's schema is one `token`, and where the server lives is
settled by `rule_for()` and `regions_for()` at composition, which is the
configuration tree feature 058 opens. There is no box on the form to put the
address in.

**Also done, and it was not in the plan.** No integration declared a default port
either, so `IntegrationProfile.default_port` was added and the six declare theirs.
Nought means "hosted, and has no default install to point at", which is what
stops a container somebody called `datadog` being offered as a Datadog endpoint.

<!-- proof: tests/unit/gateway/http/test_catalogue_ordering_and_gaps.py::test_a_vendor_the_estate_holds_comes_first_with_its_address -->
<!-- proof: tests/unit/platform/estate/test_integration_suggestions.py::test_a_hosted_vendor_with_no_default_port_is_not_suggested_from_an_address -->
<!-- handoff: to=058-configuration-write-surfaces what="prefill the endpoint field from GET /v1/integrations `suggested.address` once the configuration tree gives a self-hosted integration an endpoint field to prefill; the value is already derived and served per entry" -->

---

## 10. `GET /v1/integrations` now takes an authenticated request

**Not in the plan.**

**Done.** The handler gained an `authorized` dependency, because the suggestions
are derived from *this team's* estate and reading it needs a tenant scope.

**Why it changes nothing about who may call it.** The route table already
declared `GET /v1/integrations` as requiring `integration.manage`, and the guard
was already applied from the table. The handler simply did not name the
dependency it was already protected by. No permission was widened or narrowed;
the security suite is green unchanged.

---

## 11. The live cluster confirmation has not been run, and could not be from here

**Planned.** T-012: "Then, against HAL9000 (recorded in deviations, not in the
gate): verify all six against the real addresses — each returns data from a
recent window; the skew check reports measured offsets; the AdGuard resource's
signal map names pve-exporter for pressure."

**Not done.** There is no Proxmox cluster and no observability stack reachable
from this machine — the same fact feature 053's deviation §12 records, unchanged.
The nine addresses in `spec.md` are on a network this checkout cannot see.

**What is proven instead, and what is not.** Every mechanism the live run would
exercise runs here against the real code with a scripted vendor: the real
verifiers, the real clients, the real credential proxy with each vendor's own
injection rule, and a far side that answers on the path the client actually
calls. What that establishes is that the probes ask the right questions and read
the answers correctly. What it does not establish is that *these six servers* at
*those nine addresses* answer them — which is the half that needs the cluster.

Three things in particular are unconfirmed and worth naming, because each is a
place where a real deployment can differ from a correct implementation:

1. **The series names.** `pve_memory_usage_bytes` and its siblings are the
   pve-exporter's published names; whether this cluster's exporter build uses
   them is a fact about that cluster.
2. **The `id` label format.** The guest selector is `id="lxc/100"`, which is what
   the exporter documents. A cluster whose relabelling rewrote it would return an
   empty series — and this feature's whole argument is that an empty series reads
   like an answer.
3. **Whether any of the six sends a `Date` header** through whatever reverse
   proxy fronts it. Each that does not reports `UNREPORTED`, honestly, and the
   skew half of acceptance 4 goes unmeasured for it in practice.

<!-- handoff: to=055-alert-ingress-first-investigation what="run the six deep verifies against the real addresses in spec.md §1 from a host that can reach 10.20.20.0/24, and confirm three things a scripted vendor cannot: the pve-exporter series names in integrations/prometheus/pressure.py, the id=\"lxc/<vmid>\" label format, and which of the six send a Date header through their reverse proxy" -->

---

## 12. Delegation: the six verifiers were wired inline

**The instruction.** "Delegate on a fan-out only: three or more independent items
of the same shape."

**Done inline.** Six vendors is a fan-out by count and was not one by dependency:
every one of them wires against `DataWindowProbe`, `ClockSkewProbe` and
`client_window_probe`, none of which existed until the commit before. Six agents
starting cold against an API invented ten minutes earlier would each have had to
re-derive its shape from the same source, and any disagreement between them would
have surfaced as six subtly different probe descriptions in one report.

The `done-auditor` was run once, near the end, and what it found is in §14.

---

## 13. The mock data plane derives the signal block rather than carrying a copy

**Not in the plan.**

**Done.** `tools/mockplane/capture/projection.py::_signals` calls the real
`signal_map_for` for every projected resource, and
`tools/mockplane/dataset/served.py` serves `known_gaps` from the real
declaration.

**Why it had to be the builder and not the fixture.** The first attempt edited
`fixtures/scenarios/*/estate-resource-detail.json` by hand, and
`tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed`
caught it: a fixture the builder cannot reproduce is a fixture that disappears
the next time anybody runs `mockplane build`, taking the console assertions with
it. The check was right and the edit was wrong.

**What the dataset therefore shows, and it is worth stating.** The committed
scenario is a deployment that discovered an estate and connected nothing to
watch it, so *up* resolves to the hypervisor and the other five come back as
named gaps. That is the honest render for that deployment and it exercises the
half of the panel that matters most — a missing log store shown as nothing reads
as "there are no logs". The keyed-pressure render, which that dataset cannot
show without giving an anonymised capture a real vendor's name, is asserted
against a stub in the same file.

<!-- proof: tests/contract/fixtures/test_dataset_coherence.py::test_rebuilding_the_dataset_reproduces_what_is_committed -->

---

## 14. Gate

Recorded as it was run.

- `make lint format-check typecheck check-imports check-constants` — green.
  Mypy strict over the first-party tree, all seven import contracts kept.
- `uv run pytest tests/unit tests/contract tests/synthetic tests/architecture
  tests/security` — 12,955 passed, 18 skipped, after the three failures below
  were fixed.
- **Three things `make verify` caught that the targeted runs did not**, all of
  them generated artefacts that had gone stale against the source:
  `docs/integrations-catalogue.md` (the two new recorded gaps),
  `docs/capabilities.md` (the new `prometheus_resource_pressure` capability), and
  the mock dataset (§13). Each regenerated from its own generator rather than
  edited.
- `make verify` — **green, end to end: 13,005 passed, 25 skipped, 6m37s, exit 0.**
  Includes `check-integration-docs`, `verify_integrations` (84 integrations at
  full parity, every permission probed), both doc-drift checks, the dataset
  coherence check, and the console gate's own contract suite.
- The console gate: `console-lint`, `console-typecheck`, `console-test`
  (1,146 passing, branch coverage 90.17% against the 90% floor),
  `console-budget`, both browser projects (`behaviour` 60 passed, `first-day` 5
  passed), and the 20 visual baselines — **no baseline needed re-capturing**.
  The catalogue's gap list and the resource signal panel both render below what
  the screenshots frame, and the signal panel draws only for a selected row,
  which the captured addresses do not carry.
- `fixtures/contract/openapi.json` and `console/src/api/schema.ts` regenerated
  twice, because two routes changed shape.
- **Not run: `make test-postgres`.** Nothing in this feature touches
  `platform/persistence/`: no migration, no repository, no column. The one
  storage-adjacent change is `vmid` on two resource *kinds* (§7), which is a
  declaration read at composition and lands in the existing JSONB attributes
  column that already round-trips there.

---

## 15. What the done-audit found

Run once, near the end, against this diff and this record. It confirmed all five
Definition-of-done items, checked that every `proof` mark names a test that
exists and asserts the claimed behaviour, and mutation-checked the two claims
that carry the most weight:

- forcing `platform/estate/signal_map.py::_key_for` to return the empty string
  fails 25 tests with real assertion errors across four files — not collection
  errors, not silent passes;
- forcing `DataWindowOutcome.usable` to return `True` unconditionally fails 8,
  the same way.

It raised three things and was right about all of them.

**`make verify` was not green.** Two generated documentation pages were stale
against source this feature changed. Both regenerated — see §14. This is the
finding that mattered: the targeted suites were all green, and would have stayed
green through the close.

**§12 pointed at a section that did not exist yet.** It claimed the audit had run
and referred to a placeholder. Now it refers to this section, written after the
audit rather than before it.

**Item 1 is met for four of the six literally and for two of them in the sense
§2 records** — Alertmanager and Grafana prove the query path rather than a
windowed read, because neither API has a window. The auditor read the deviation
as honest rather than as cover, which is the reading it was written for; the
sentence in `tasks.md` is nevertheless not literally true of those two, and this
line is here so that nobody has to re-derive that from the code.

---

## 16. The close failed on eight proof marks, and the marks were wrong rather than the tests

**What failed.** The close reported eight `proof` marks citing tests that "do not
exist". All eight existed and all eight passed. Every one of them named a test
*method inside a class*:

```
tests/unit/platform/estate/test_signal_map.py::TestTheRestOfTheMap::test_up_is_answered_by_whatever_declares_the_resource_exists
```

**What the mark format actually is.** A `proof` mark carries one field, and that
field is a file and a test name — `test_signal_map.py::test_up_is_answered_by_...`
— two parts, not three. A pytest node id that names a class in the middle is not
that shape, and the checker resolves the name against the module's own test
functions rather than walking into classes.

*Written the long way round on purpose: spelling the mark out in full, angle
brackets and all, is itself a mark. See §17.*

**How that was established without reading the checker.** By counting what every
other feature has already had accepted. Across `specs_v3/*/deviations.md` there
are 63 proof marks: 37 name a Python test, **all 37 of them a module-level
function and not one an in-class method**; the rest are console files cited with
no `::` at all, which the checker also takes. 054 was the only feature in the
repository that wrote a class segment, and its eight class-qualified marks were
exactly the eight the close rejected. Its own two marks that passed
(`test_a_source_whose_ordinary_state_is_empty_is_not_reported_as_broken` and
`test_a_windowed_read_asks_for_the_window_rather_than_all_of_history`) are
`@pytest.mark.parametrize`d, so parametrisation is not what the checker minds —
the class is.

**Done.** The seven cited methods are now module-level tests, and the eighth mark
— which named a bare *class*, `TestEveryResourceResolvesTheTwoThatMatter`, with no
test at all — became the two tests it stood for. Renamed where the class name was
carrying part of the sentence, so each still reads on its own:

| was | is |
|---|---|
| `TestAnEmptyWindowThatIsTheCorrectAnswer::test_the_report_says_why_empty_is_not_a_finding_here` | `test_an_expected_empty_window_says_why_empty_is_not_a_finding_here` |
| `TestAClockInsideTheTolerance::test_a_source_that_agrees_verifies_with_the_measured_offset` | `test_a_clock_inside_the_tolerance_verifies_with_the_measured_offset` |
| `TestASourceThatReportsNoTime::test_the_report_says_it_could_not_be_measured_not_that_it_agreed` | `test_an_unmeasured_clock_is_reported_as_unmeasured_not_as_agreeing` |
| `TestAVendorThatIsNotASignalSource::test_the_record_carries_the_new_probes_only_when_they_ran` | `test_the_record_carries_the_new_probes_only_when_they_ran` |
| `TestPressureOnAContainerComesFromTheHost::test_a_guest_the_estate_holds_no_identifier_for_is_a_named_gap` | `test_pressure_for_a_guest_with_no_identifier_is_a_named_gap` |
| `TestTheRestOfTheMap::test_up_is_answered_by_whatever_declares_the_resource_exists` | unchanged, now module-level |
| `TestWhatItRefusesToGuess::test_a_hosted_vendor_with_no_default_port_is_not_suggested_from_an_address` | unchanged, now module-level |
| `TestEveryResourceResolvesTheTwoThatMatter` (a class) | `test_every_resource_answers_or_names_up_and_logs` **and** `test_with_nothing_configured_up_and_logs_are_named_gaps_rather_than_silence` |

No assertion changed. The three files collect and pass the same 56 tests they did
before, and the count is the check: a promotion that dropped a test would show up
as 55.

**What was deliberately not done.** The remaining classes in those files are left
alone. Grouping tests in classes is an established minority pattern here — 13
files and 220 tests use it, most of them written long before this feature — and
`tests/unit/tools/test_check_raw_sql.py` already mixes module-level tests with a
class, so the result is not a shape the repository has never seen. Dissolving
four files' worth of classes to suit a mark format would have been a taste
change wearing a gate failure as justification.

**The rule worth carrying forward.** A `proof` mark addresses a *module-level
test function*. If a behaviour worth citing lives inside a class, promote it —
the mark cannot reach into the class, and a mark that cannot be resolved is
counted as a claim with no proof rather than as a mark with a typo.

**Gate, re-run after this change.** `make verify` green end to end — 13,005
passed, 25 skipped, 6m22s, exit 0 — the same counts §14 recorded before the
promotion, which is what a rename that moved no assertions should produce. The
console gate is unchanged and needed no baseline re-capture.

---

## 17. The repair introduced one more dangling mark, by documenting the mark syntax

**What happened.** §16 explained the mark format by writing an example of it out
in full — angle brackets, `proof:`, and a `tests/path.py::test_name` placeholder.
The checker does not read markdown. It scans for the comment syntax, and an
example of a mark inside a sentence is a mark. So the section written to explain
why eight marks did not resolve created a ninth that did not resolve, citing a
file that was never meant to exist:

```
- proof cites tests/path.py::test_name, which does not exist
```

**Worth naming: the evidence was already in hand.** The script written to check
the eight repairs printed `FILE MISSING: tests/path.py::test_name` in the same
run that confirmed the other fifteen marks were good. It was read as noise from
the prose and waved off, which is precisely the mistake this feature is about —
a checker returning a real finding, and a human deciding it did not count.

**Done.** §16 now describes the shape in words and shows only the payload, with
no comment syntax anywhere in it. A validation pass over every mark in this file
resolves, and the placeholder is gone.

**The rule.** Do not write a mark's literal syntax in prose, not even as an
example. Anything that reads as a mark is one, and the record is machine-read
before it is human-read.
