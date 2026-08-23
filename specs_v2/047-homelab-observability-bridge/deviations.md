# Deviations — 047 Homelab Observability Bridge

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. The bridge is a package, not a module in `platform/observation/sources/`

**Planned.** The technical-context table says "a bridge module in
`platform/observation/sources/`".

**Done.** `platform/observation/bridge/` — fourteen modules: `ports.py`,
`errors.py`, `verification.py`, `mapping.py`, `exporters.py`, `catalogue.py`,
`history.py`, `precedence.py`, `availability.py`, `alerts.py`, `logs.py`,
`dashboards.py`, `rules.py`, `hosting.py`, `supplementary.py`, `provenance.py`,
`config.py`.

**Why.** `sources/` is where a `SignalReader` lives, and exactly one thing in
this feature is one — `history.py`'s `MetricsHistorySource`, which is placed
there in spirit and reachable from the tick unchanged. The other thirteen are
not sources at all: an alert correlator, a log reader, a dashboard link builder,
a duplication report over somebody else's alert rules. Putting them under
`sources/` would have made the word mean "anything to do with a provider", which
is how a package stops being a boundary.

The plan's own phase list is the argument: seven phases, of which one is about
signal sources. The rest needed somewhere else to live, and `bridge/` is the
name the plan itself already uses for the thing.

---

## 2. The webhook route is not rewired to use the bridge's correlation

**Planned.** The technical-context table says the alert path is "the existing
`/webhooks/alertmanager` route, rewired by feature 039 to raise incidents".

**Done.** `alerts.py` correlates an alert to the estate resource it names, opens
an uncorrelated incident when it cannot, respects the source's own grouping key,
and closes on resolution as source-resolved. Every one of those is proven
against the real `IncidentLifecycle` and the real store. **`gateway/webhooks/
router.py` is unchanged** and still raises through feature 039's own
`raise_for_alert` with the alert's own components as subjects.

**Why.** NFR-004 is the reason and it is load-bearing: "Nothing here may become a
required dependency of features 038, 039 or 044." The webhook router *is*
feature 039's surface. An import of `platform.observation.bridge` in it would
make the alert-ingestion path of a deployment with no observability stack at all
depend on this feature — which is precisely the dependency the requirement
forbids, and it would be invisible because the enrichment degrades to nothing
when the estate matches nothing.

The correlation also needs two things the route does not hold: the node's
resolved bridge configuration, and an estate read per alert. Both are composition
decisions, and this repository already treats composition as feature 030's
concern in exactly this shape — `surfaces/cli/client.py`'s `LocalServices`,
`gateway/http/services.py`'s `InvestigationRunner`, and feature 039's own
deviation §7, which left the same route starting runs directly rather than
moving an ASGI lifespan into `platform/`.

**What this means for the definition of done.** FR-009's correlation, FR-010's
source-resolved close and FR-011's grouping are implemented and proven as
library behaviour, reachable in one call. They are not yet reached *from the
HTTP route*, and a deployment wanting them there wires `raise_for_incoming_alert`
into its own composition root. That is a real gap and it is deliberate; the
alternative was breaking NFR-004 to close it.

FR-008 — "no second path" — is fully satisfied either way, and is asserted
structurally: `alerts.py` constructs no `Incident` and no `IncidentRaise` of its
own, and a test parses its AST to keep that true.

---

## 3. The definition of done's real-cluster item cannot be satisfied

**Planned.** "Shipped exporter mappings verified against a real Proxmox
exporter."

**Done.** The shipped mappings are verified against the label *shapes*
`prometheus-pve-exporter` and `node_exporter` publish — `id="lxc/100"`,
`id="node/pve01"`, `id="storage/pve02/local-lvm"`, `instance="pve01:9100"` —
using the reference cluster's own identifiers from the field baseline: CT100,
`TeraChad`, `pve01`, `pve02`, the `data-pool` thin pool at 31.98% metadata, and
the failed `corosync-qdevice.service`. Nothing has been run against a live
exporter.

**Why.** There is no cluster reachable from `make verify`, and there is no
cluster-backed harness in the repository to hang the run on — feature 049 is the
one that builds it, and it is later in this wave. This is the same disposition
feature 046 recorded for the same reason.

**What this means.** The item is genuinely unmet. The mappings are written from
the exporters' published label schemes and are tested against them; pointing
them at a live Prometheus later is a change of transport rather than a change of
rule, because the transport is a protocol (`MetricsSource`) with no
vendor knowledge in it.

---

## 4. Mapping addresses the estate's *native* identity, through a pattern

**Not in the plan.** The plan says "declared label rules" and nothing about what
a rule resolves to.

**Done.** A rule declares a template over labels — `lxc/*/*/{id:-1}` — that
resolves to a **native-identity pattern**, matched against the estate.

**Why it had to.** `platform/estate/identity.py` hashes a resource id from
`(source, native_id)` into `res-<32 hex>`. A label set can reconstruct
"container 100" and can never reconstruct a digest, so a rule resolving directly
to a resource id was not available. And a Proxmox guest's native identity
deliberately carries its *creation time* — that is what keeps VMID 100 distinct
from the VMID 100 before it — which no metric label carries either.

So the parts a metrics system cannot know are wildcards, one segment each. On a
single cluster that resolves exactly. Where it does not, the consequences are
declared rather than guessed:

| Situation | What happens |
|---|---|
| One match, absent | It maps. Metrics outlive guests, and the series is about the guest that was destroyed |
| One live, one absent | The live one wins — what is publishing now is what is running now |
| Two live | Reported as ambiguous, with both native identities named |

The template grammar is `{label}`, `{label:host}` and `{label:<index>}` and has
no fourth form, for the reason a detector has four condition kinds: anything
more expressive is an interpreter nobody can validate.

---

## 5. Precedence applies only where coverage is genuinely duplicated

**Planned.** FR-006: "Where the deployment polls for something the metrics source
also provides, precedence MUST be declared, and only one MUST produce signals."

**Done.** `SignalPrecedence.producers` resolves per signal: a signal only one
source declares is produced by that source whatever the rules say, and only a
signal two sources both declare is decided by precedence. The default winner for
an undeclared duplicate is the deployment's own polling.

**Why it is written down.** The first implementation applied the default
everywhere, which meant enabling the bridge silenced every bridge-only signal
before it produced anything — a detector that never fires for a reason nothing
states. The requirement's own wording is "where the deployment polls for
something the metrics source *also* provides", and that "also" is the whole rule.

The default favouring polling is what makes FR-023 hold: enabling a source adds
signals and takes none over until somebody says so, so pasting a Prometheus URL
cannot change which detectors fire.

---

## 6. Two constants modules' worth of numbers went to a new domain module

`config/constants/observability_bridge.py` — mapping bounds, the mapping
schedule, history lookback and step, log window and line bounds, dashboard link
padding, the precedence vocabulary, the view vocabulary, the three exporter
names and the Proxmox estate-source name.

**Why not `config/constants/observation.py`.** That module's own docstring says
what it is: "a bound on the deployment's own appetite rather than on a remote
system's". Every number here is the opposite — each one protects a system this
deployment does not own and cannot restart. `config/AGENTS.md` says a new bound
goes in the domain module that owns it, and the existing one explicitly disowns
this domain.

`PROXMOX_ESTATE_SOURCE` is there for a duller reason: the shipped rules address
the Proxmox integration's native identifiers, `config/` imports nothing
first-party, and tier 3 cannot import the tier-2 package that owns the string
either. A constant is the only place it can live.

---

## 7. Configuration went under `policies.observation.bridge`

**Not specified.** The plan says "declared label rules in configuration".

**Done.** `ObservabilityBridgeSettings` on `ObservationPolicySettings`, with six
nested section types.

**Why there.** `platform/config_service/schema/root.py` declares six sections
and says why the closure matters. Feature 039 put detectors under
`policies.observation` for the same reason, and its deviation §3 records it: this
is a policy — whether this team joins its own monitoring to the estate — not a
seventh top-level concern.

`when_labels` is a list of `label=prefix` strings rather than a mapping, so that
every field in the document stays renderable as a form. It is parsed in
`bridge/config.py`, which reports an unparseable entry rather than raising, the
same way the detector resolution does.

---

## 8. Verification attributes exporters by metric name, and the matchers are
   therefore bare metric names

**Not in the plan.**

**Why it is worth recording.** A metrics source answers a multi-selector query
with a flat list of series and does not say which selector produced each one.
Attributing them by prefix looked obvious and was wrong: `node_uname_info` and
`node_textfile_mtime_seconds` share a prefix, so the textfile collector would
have verified as absent on every node that has one — an exporter reporting
missing while publishing, which is the worst of the four possible answers.

So attribution is by exact metric name, and every shipped expectation's matcher
is a bare metric name. The constraint is stated in `_counts`' docstring, because
the next person to write a filtered selector will read that first.

---

## 9. `_handle_resolution` in the gateway keeps feature 039's wording

`platform/observation/bridge/alerts.py` records a source resolution as
`"the source that raised it reported it resolved: alertmanager"` through
`IncidentLifecycle.close`. The gateway's existing path uses `self_close` with
`"<alert> was resolved upstream"`, which records the same fact in 039's own
words.

Not unified, for the reason in §2: touching that route is what NFR-004 forbids.
Both are recorded on the timeline and both name the upstream, so an operator
reading a closed incident can tell source-resolved from our own recovery
condition holding either way.

---

## Not deviations, recorded because they look like they might be

- **`ResourceSeries.matcher` writes a query.** The bridge is otherwise
  scrupulous about not knowing any query language — matchers and selectors are
  opaque strings the caller supplies. This one property builds
  `metric{label="value"}`, and it is the exception FR-004 requires: the
  alternative is an investigation composing selectors, which is the thing the
  requirement exists to prevent. It is the label-matcher form every
  Prometheus-compatible source accepts, and it is the only grammar this package
  writes.

- **Three `except Exception` blocks.** In `verify_metrics_source`,
  `verify_log_source` and `dashboard_link`. Each is deliberately broad and each
  says so beside a `noqa`: whatever a transport managed to raise, the outcome
  that must not follow is a verification that reports clean because it never got
  an answer, or a report that silently has no link.
  `platform/observation/evaluation.py` already does exactly this for a detector
  that throws, for the same reason.

- **The self-hosting check matches on display names.** Correlating a scrape
  endpoint to a guest by asking every guest for its addresses would be a sweep
  this feature has no business making, and a homelab operator names the container
  running Prometheus "prometheus". The check reports; it never refuses to use a
  self-hosted source, because refusing would leave the deployment with less
  information than it had.

- **`published_readings` returns a mapping with keys absent rather than empty.**
  That is the contract `integrations/proxmox/supplementary.py` was written
  against in feature 044 — a missing key becomes "unavailable, and here is what
  would publish it", an empty value becomes "nothing is failing". The two are
  opposite claims and only one of them can be made about a node nobody watches.
  A contract test drives the real integration module over the real bridge output
  to prove the two halves agree.

- **The mapping bound is on series *considered*, not series mapped.** Bounding
  the mapped count would let an unconfigured Prometheus with a million unmapped
  series run the pass to completion every time. Both counts are reported.

- **Test-first, per module rather than per phase.** The same sequencing features
  020 §7 and 021 §7 recorded, for the same reason: a suite written against
  modules that do not exist can only fail on `ImportError`, which proves nothing
  about the behaviour it describes. Each module's tests were written, run and
  confirmed failing before the module existed — the mapping suite was red against
  a missing `platform.observation.bridge.mapping`, then red on the ambiguity and
  destroyed-guest cases, then green.

## Gate

`make verify` green: lint, format-check, mypy strict over 1,640 files, all seven
import contracts, every guard script, the console gate, and **11,914 passed, 22
skipped** — 96 tests added, no pre-existing failures before or after, and no
generated documentation drifted.
