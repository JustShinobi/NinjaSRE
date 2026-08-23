# Feature 032 — Mock Data Plane

- **Wave:** 9 — Console rework
- **Branch:** `feat/032-mock-data-plane`
- **Status:** Draft
- **Depends on:** none — this is the first feature of the second wave

## Summary

A coherent, deterministic, anonymised dataset describing a real deployment, and
a mock API that serves it over the same contract the gateway serves — so the
console can be built, reviewed and regression-tested without a backend, a
cluster, a database or a model.

**This lands first because everything after it depends on data that does not
exist yet.** A screen cannot be designed against an empty array. A reviewer
cannot judge whether a dashboard reads well when every tile says zero. And a
visual-regression baseline captured against live data is not a baseline — it is
a photograph of one moment, and it will differ on the next run because a
timestamp moved. The fidelity clauses in features 034 through 037 require the
built console to match the mockups; that comparison is only meaningful against
fixed data.

The dataset is **derived from a real capture of the reference cluster**, not
invented. Real infrastructure has properties invented data never has: 84 guests
where two are virtual machines and the rest containers, load skewed heavily onto
one node, three guest volumes above 93% while their datastore reads 84%, a backup
job that exists and is disabled, nine failed units on one host, and two
datastores answering `unknown`. A console that looks right against tidy data and
falls apart against that is a console that has not been tested.

Everything identifying is removed. What survives is shape, scale, distribution
and the awkwardness — which is the part that has design value.

## User scenarios

### Primary story

A contributor clones the repository, runs one command, and has the console
running against a full deployment: an estate of ninety-odd resources, open
incidents, completed investigations with real transcripts, approvals waiting,
episodes, strategies, a topology, an audit trail. No cluster, no database, no
API key, no network.

They switch scenario with a flag and get the same console on a brand-new
deployment with nothing in it, then on one where half the panels are failing,
then on one with ten thousand runs. Each takes a second and each is exactly the
same every time.

A reviewer opens a pull request. The visual diff shows three screens changed,
and it is trustworthy, because the only thing that differed between the two runs
was the code.

### Acceptance scenarios

1. **Given** a real deployment, **when** the capture command runs, **then** it
   produces a raw fixture set covering every endpoint the console consumes.
2. **Given** a raw capture, **when** anonymisation runs, **then** no hostname,
   address, personal name, domain, credential, key, token, MAC address or
   real guest name survives it — asserted by a scan that fails on any match.
3. **Given** anonymisation, **when** the same input is processed twice, **then**
   the output is identical, and one real entity maps to one pseudonym everywhere
   it appears.
4. **Given** the anonymised dataset, **when** referential integrity is checked,
   **then** every reference resolves — a run names resources that exist, an
   episode names the run that produced it, an incident names subjects in the
   estate, a topology connects resources that exist.
5. **Given** the mock API, **when** the console calls it, **then** the responses
   validate against the gateway's OpenAPI document, and a schema change that
   breaks a fixture fails the build.
6. **Given** a scenario, **when** it is served twice, **then** the responses are
   byte-identical, including every timestamp.
7. **Given** the empty scenario, **when** the console renders, **then** every
   screen shows its empty state, which is how the empty states get reviewed at
   all.
8. **Given** the failure scenario, **when** the console renders, **then**
   individual endpoints fail in declared ways — slow, refused, 500, 403, 404,
   truncated — and the panel-level error handling is exercised.
9. **Given** a live run in a scenario, **when** the console subscribes, **then**
   the mock streams events over the real transport, at a controllable rate, with
   a controllable disconnection.
10. **Given** the scale scenario, **when** the console renders, **then** it holds
    a ten-thousand-event transcript, ten thousand runs, ten thousand resources
    and a five-hundred-node configuration tree.
11. **Given** the dataset, **when** feature 042 seeds demo mode, **then** it loads
    **this same dataset** into the real database. There MUST NOT be two fictional
    deployments.
12. **Given** any mock, **when** a test runs, **then** no request leaves the
    machine; a real network call fails the test.

### Edge cases

- A capture taken from a deployment with a feature the fixtures do not model.
- An endpoint the console consumes that the capture missed.
- A pseudonym that collides with another entity's pseudonym.
- Anonymisation that breaks a reference — two names that had to stay equal.
- A guest name that is itself a piece of software everyone runs, where the name
  is not identifying but the combination is.
- A capture containing a secret in a field nobody expected.
- Fixtures that drift from the API after a gateway change.
- A scenario file large enough to slow the test suite.

## Requirements

### Functional

**Capture — two sources, because one is not enough yet**

This feature is first in the wave, which means most of what the console will
show does not exist behind the gateway yet. Estate, incidents, detectors and
autonomy policy arrive with features 038, 039 and 040; Proxmox discovery arrives
with 044. A capture that read only the gateway would produce runs, memory,
configuration and audit — and none of the resource inventory, health, storage
pressure or incidents the screens are built around. So the capture reads two
places and merges them.

The second source is **SSH to the cluster nodes**, not the REST API. Two reasons,
and the second is the one that decided it. `pvesh --output-format json` returns
exactly what REST returns, so nothing is lost on the endpoints the API covers.
And the endpoints it does not cover are not an afterthought — failed units, thin
pool metadata, mount state and boot history are absent from REST, and they are
precisely where the reference cluster's only total outage was visible.

- **FR-001** A capture command MUST record real responses from a running
  NinjaSRE deployment for every endpoint the console consumes **that the gateway
  already serves**, and MUST report every console-consumed endpoint it did not
  reach.
- **FR-001a** For the endpoints the gateway does not serve yet, the capture MUST
  read the **cluster directly over SSH**, and project the result into the shape
  those endpoints will return. The projection MUST be written against the
  response schemas features 038 and 039 declare, so the fixtures are wrong in the
  same way the future endpoints would be wrong, rather than in a way of their
  own.
- **FR-001b** Within the SSH session, anything the Proxmox API can answer MUST be
  read through `pvesh ... --output-format json`, not by parsing CLI text. `pvesh`
  is the same API the REST endpoint serves, so those payloads are byte-identical
  to what feature 044's client will return — which is what makes them reusable
  when it lands.
- **FR-001c** Reads the API cannot answer MUST be taken from the shell. This is
  the reason SSH is the transport rather than REST, and it is not a small
  residue: failed `systemd` units, LVM thin-pool **metadata** percentage,
  `corosync.conf` as written, mount state, and boot history are all absent from
  the REST surface, and every one of them is a shipped detector in feature 048 or
  a finding in the reference cluster's own postmortems.
- **FR-001d** Each captured record MUST state how it was obtained — gateway,
  `pvesh`, or shell — so a projected record is never mistaken for one the gateway
  returned, and so the two classes can be told apart when the real endpoints
  arrive.
- **FR-001e** The capture MUST be **read-only against the cluster**. Commands MUST
  come from a declared allowlist; a command outside it MUST fail the capture
  rather than run. No command may write, restart, migrate, or alter any state.
- **FR-001f** The allowlist MUST be extensible by the operator, and adding to it
  MUST be a reviewable change to a declared file rather than a flag. The point of
  SSH is that a question nobody anticipated can still be asked; the point of the
  allowlist is that answering it stays a decision somebody made.
- **FR-001g** Connection details MUST come from configuration, never from source.
  The reference cluster's topology — node addresses, cluster name, guest and
  storage inventory — is recorded in
  [`../044-proxmox-integration/cluster-baseline.md`](../044-proxmox-integration/cluster-baseline.md);
  the SSH identity is supplied at run time and is never written down here.
- **FR-001h** Once features 038, 039 and 044 have landed, re-running the capture
  MUST take the `pvesh`-derived records from the gateway instead, and that part
  of the direct path MUST be removed rather than kept as a second way to produce
  the same fixture. The shell-derived records have no gateway equivalent and stay
  — which is itself a finding worth carrying into feature 045: a Proxmox
  integration limited to the REST API cannot see the layer the reference
  cluster's only total outage lived in.
**Asking the source a new question**

The capture answers the questions somebody thought of in advance. Building a
console against real infrastructure keeps producing questions nobody thought of
— what does a locked guest's config actually look like, what does the task log
say when a backup dies, how does this node report a degraded mount. Sending
somebody to a terminal to find out, and then transcribing the answer by hand, is
how a fixture ends up describing what a person remembered rather than what the
cluster said.

- **FR-001i** The same read-only channel MUST be usable as an **ad-hoc query
  tool**, not only as a batch capture: one command, one allowlisted read, the
  answer on stdout.
- **FR-001j** An ad-hoc query MUST be recordable into the fixture set by the same
  path a captured one takes — same anonymisation, same source attribution, same
  referential check. A finding that reaches the dataset by a different route is a
  finding the scan never saw.
- **FR-001k** Ad-hoc queries MUST obey FR-001e's allowlist and FR-001f's
  extension rule without exception. A convenience escape hatch here would make
  every other guarantee in this section advisory.

- **FR-002** The capture MUST record the raw response, the request that produced
  it, and the contract version in force.
- **FR-003** Raw captures MUST be treated as sensitive: never committed, never
  logged, and deleted by the pipeline once anonymised output exists. This applies
  to the direct infrastructure read with more force than to the gateway read —
  it carries guest configuration, addresses and, potentially, cloud-init
  secrets.

**Anonymisation**

- **FR-004** Anonymisation MUST replace every identifying value with a stable
  pseudonym: hostnames, node names, guest names, IP and MAC addresses, domains,
  URLs, e-mail addresses, personal names, principal identifiers, team names,
  storage names, pool names, cluster names, and free-text fields that carry any
  of them.
- **FR-005** Pseudonymisation MUST be **deterministic and consistent**: one real
  value maps to one pseudonym everywhere it appears, across every file, so
  references survive.
- **FR-006** The mapping MUST NOT be committed, MUST NOT be derivable from the
  output, and MUST NOT be reversible without it.
- **FR-007** Anything credential-shaped MUST be removed rather than
  pseudonymised: tokens, keys, certificates, passwords, cloud-init blocks,
  connection strings, authorisation headers.
- **FR-008** Anonymisation MUST preserve **shape, scale and distribution**: the
  count of each resource kind, the ratio between them, utilisation percentages,
  timestamp intervals, payload sizes, error rates, and the skew between nodes.
  These are what the console is being designed against.
- **FR-009** Anonymisation MUST preserve the **awkward** properties, explicitly:
  near-full volumes, disabled jobs, failed units, unknown statuses, coverage
  gaps, and long identifiers. A tidied dataset defeats the purpose.
- **FR-010** Timestamps MUST be shifted to a fixed reference instant while
  preserving every interval between them, so the dataset is deterministic and
  still reads as a coherent history.
- **FR-011** A verification scan MUST run over the anonymised output and fail on
  any occurrence of a real identifier, address, domain or secret pattern. The
  scan MUST be part of the gate, not a manual step.
- **FR-012** Re-running the pipeline on the same capture MUST produce
  byte-identical output.

**Coherence**

- **FR-013** The dataset MUST be referentially complete: every identifier
  referenced by any record MUST resolve to a record that exists.
- **FR-014** A referential-integrity check MUST run in the suite and name the
  broken reference when it fails.
- **FR-015** The dataset MUST be internally plausible as a history: a run's
  events ordered, an incident opened before it closed, an episode created after
  the run that produced it.

**Contract fidelity**

- **FR-016** Every fixture response MUST validate against the gateway's OpenAPI
  document for its endpoint.
- **FR-017** A contract change that invalidates a fixture MUST fail the build,
  naming the endpoint and the field.
- **FR-018** The fixture set MUST cover every endpoint the console consumes; an
  uncovered endpoint MUST fail a coverage test.

**Scenarios**

- **FR-019** The dataset MUST be organised into named scenarios, selectable by
  one flag or environment variable, at minimum:
  - **`populated`** — the default; a full deployment mid-operation, with open
    incidents, waiting approvals, running and completed runs.
  - **`empty`** — a brand-new deployment with nothing in it.
  - **`first-run`** — configured but incomplete, so the setup checklist renders.
  - **`degraded`** — several endpoints slow, refused, or answering 500 and 403.
  - **`scale`** — the volumes feature 036's benchmarks declare.
  - **`incident-live`** — a run in flight, streaming.
  - **`restricted`** — a viewer-role principal, for the role-matrix screens.
- **FR-020** Scenarios MUST be composable with per-endpoint overrides, so a test
  can take `populated` and make one endpoint fail.
- **FR-021** Adding a scenario MUST NOT require changing the console.

**The mock API**

- **FR-022** A mock server MUST serve the fixture set on the same paths, methods
  and status codes as the gateway.
- **FR-023** It MUST support the streaming transport, with controllable event
  rate, controllable mid-stream disconnection, and controllable replay after
  reconnect — the three behaviours feature 037's reducer is proved against.
- **FR-024** It MUST support injected latency, injected failure and injected
  empty responses, per endpoint.
- **FR-025** Writes MUST be accepted and reflected in subsequent reads within a
  session, so optimistic updates and approvals can be exercised, and MUST reset
  between sessions.
- **FR-026** It MUST refuse any outbound network call and MUST fail loudly rather
  than falling through to a real service.
- **FR-027** It MUST be startable in one command for development and
  programmatically for tests.

**Shared with demo mode**

- **FR-028** This dataset MUST be the single source for feature 042's demo mode.
  The demo seeder loads it into the real database rather than defining its own.
- **FR-029** Records loaded into a real deployment MUST carry feature 042's
  demonstration label.
- **FR-030** A test MUST assert there is exactly one fictional deployment in the
  repository.

### Non-functional

- **NFR-001** Loading any scenario MUST complete within a declared budget; the
  console's development loop MUST NOT wait on it.
- **NFR-002** The committed dataset MUST stay within a declared size budget; the
  `scale` scenario MUST be generated from a seed rather than committed in full.
- **NFR-003** The mock MUST require no service, no container and no network.
- **NFR-004** The pipeline MUST be re-runnable against a fresh capture as a
  routine operation, so fixtures are refreshed rather than left to rot.
- **NFR-005** No committed file may name the real deployment, its operator, its
  domains, or its addresses.

## Success criteria

- **SC-001** A capture produces fixtures for every console-consumed endpoint
  across both sources, and names any it missed, per source.
- **SC-001a** Every fixture record states which source produced it, and a
  projected record cannot be read as one the gateway returned.
- **SC-001b** The projected endpoints are exactly the set features 038, 039 and
  044 will serve — asserted against the endpoint split, so a projection for an
  endpoint the gateway already serves fails the suite.
- **SC-002** The identifier scan finds nothing in the committed dataset —
  asserted against a list of the real cluster's actual names, addresses and
  domains held outside the repository.
- **SC-003** Anonymisation is deterministic: two runs on one capture are
  byte-identical.
- **SC-004** One real entity has one pseudonym across every file, asserted.
- **SC-005** Referential integrity holds; a seeded broken reference fails the
  check with the reference named.
- **SC-006** Every fixture validates against the OpenAPI document; a seeded
  contract change fails the build naming endpoint and field.
- **SC-007** Every declared scenario loads and renders every console screen.
- **SC-008** The `empty` scenario renders an empty state on every screen — this
  is how feature 036's SC-001 is actually exercised.
- **SC-009** The `degraded` scenario exercises panel-level error handling on
  every screen that fetches.
- **SC-010** Serving one scenario twice produces byte-identical responses,
  timestamps included.
- **SC-011** The streaming mock reproduces disconnection and replay, and feature
  037's reducer passes against it.
- **SC-012** A real outbound request from any mock fails the test.
- **SC-013** Feature 042's demo mode loads this dataset; a test asserts no second
  fictional deployment exists.
- **SC-014** Scenario load and dataset size budgets hold.

## Out of scope

- Fixtures for the Python integration tests, which already record their own.
- Generating synthetic incidents for evaluation — feature 049.
- Anything that runs in production. This is a development and test facility.
