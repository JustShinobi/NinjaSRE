# Plan — 032 Mock Data Plane

## Technical context

| Concern | Choice |
|---|---|
| Location | `fixtures/` at the repository root — consumed by the TypeScript console, the Python demo seeder and the test suites, so it belongs to none of them |
| Format | JSON per endpoint per scenario, plus a manifest naming scenarios and their overrides |
| Capture — gateway | A Python command using the existing gateway client, run against a live NinjaSRE deployment by its operator |
| Capture — infrastructure | Read-only SSH to the cluster nodes: `pvesh --output-format json` for anything the API covers, shell for what it does not, projected into the shapes features 038 and 039 declare |
| Command safety | A declared read-only allowlist. A command outside it fails the capture; extending it is a reviewable change to a file, not a flag |
| Ad-hoc queries | The same channel, one read at a time, recordable into the fixture set through the same anonymisation path |
| Connection details | Read from configuration at run time. The reference topology is in `../044-proxmox-integration/cluster-baseline.md`; the SSH identity never appears in the repository |
| Anonymisation | A deterministic pipeline: keyed pseudonym derivation, an allowlist of preserved fields, a denylist of dropped ones, then a verification scan |
| Mock server | A small in-process server for tests and a standalone one for the development loop, both reading the same manifest |
| Validation | The gateway's committed OpenAPI document, the same copy feature 033 generates the client from |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| IV — Secrets never reach the agent | A capture from a live deployment is the most secret-dense artefact this repository will ever handle. | FR-003: raw captures are never committed and are deleted after processing. FR-007 drops anything credential-shaped rather than pseudonymising it. FR-011's scan is a gate, so a leak fails the build rather than being noticed later. |
| X — The operator owns their data | The dataset describes somebody's home infrastructure. | Nothing identifying survives, and NFR-005 forbids naming the deployment, its operator, its domains or its addresses in any committed file. The pseudonym map stays with the operator. |
| I — Evidence over assertion | Fixtures could be wishful. | FR-008 and FR-009 preserve real distributions and the awkward cases. A dataset where everything is healthy would let the console pass review while being untested against what it will actually meet. |
| XII — Test-first | This feature is itself test infrastructure. | The identifier scan, the referential-integrity check and the contract validation are all written before the pipeline that must satisfy them. |
| XIII — Language and attribution | New committed files. | British English; no upstream project named; no real deployment named. |

## Architecture decisions

**Derived from a real capture, not invented.** Invented fixtures encode the
author's idea of what infrastructure looks like, which is tidy, evenly
distributed and mostly healthy. The reference cluster is none of those: two
virtual machines against eighty-two containers, one node carrying nearly all the
running load, a guest at 99.6% of its own volume while its datastore reads 84%, a
backup job that exists and is switched off. Those are the cases the console has
to survive, and they are the ones nobody thinks to invent.

**Two capture sources, and a plan to lose half of one.** Reading only the
gateway would have been cleaner and would have produced fixtures with no estate,
no incidents and no storage pressure — fixtures for none of the screens this wave
is about. Reading the cluster directly fills that gap, at the price of a
projection layer aimed at response shapes features 038 and 039 have not built
yet. FR-001h requires the `pvesh`-derived half of that path to be *deleted* when
the real endpoints arrive; a fallback is how two sources of truth start. The
shell-derived half has no gateway equivalent and stays.

**SSH rather than REST, decided on reach rather than convenience.** The initial
instinct was the REST API: same transport feature 044 will use, scoped read-only
token, no shell. Two facts overturned it. `pvesh --output-format json` is the
same API behind the same JSON, so nothing is lost where REST would have served.
And REST does not expose failed `systemd` units, LVM thin-pool metadata
percentage, `corosync.conf` as written, or mount state — which is not a marginal
gap, because the reference cluster's only total outage was invisible at every
API level and obvious at exactly that one.

The cost is real and is paid deliberately: SSH is a far larger authority than a
read-only token. It is bounded three ways. The allowlist makes read-only a
property of the tool rather than of the operator's care. The tool lives in
`tools/`, is run by a human, and is never reachable from the agent runtime. And
feature 044's production client stays REST-through-the-credential-proxy —
Article IV forbids the agent holding an SSH identity, and nothing here changes
that. What this decision establishes is that a *development* capture may use
SSH, not that the product may.

**The channel doubles as a question-answering tool.** Building against real
infrastructure keeps raising questions the capture did not anticipate. FR-001i
to FR-001k make asking one a first-class operation that lands in the dataset
through the same anonymisation and the same scan — because the alternative is
somebody reading a terminal and typing what they remember into a fixture.

**Anonymisation preserves distribution, not just structure.** It would be easy to
normalise while renaming — round the percentages, even out the node balance, drop
the failed units. That would produce a clean dataset and destroy the entire
reason for capturing a real one. The rule is: replace identity, keep everything
else, and keep the awkwardness explicitly.

**Pseudonyms are deterministic and consistent, and the map does not ship.** A
keyed derivation gives the same pseudonym for the same input every time, so
references survive and reruns are byte-identical, while the key stays with the
operator and the output is not reversible without it. Random renaming would break
every reference; a committed map would make anonymisation theatre.

**The scan is the gate.** Anonymisation logic will have holes — a free-text
field, a URL inside a log line, a hostname in an error message. The defence is
not a more careful pipeline, it is an adversarial scan over the output that knows
the real values and fails the build on any of them. The list of real values lives
outside the repository, supplied by the operator at scan time.

**Timestamps shift, intervals hold.** Every timestamp moves to a fixed reference
instant by one offset. The dataset is then deterministic — required for visual
regression — and still reads as a coherent history, because "four minutes ago"
and "two days ago" stay four minutes and two days apart.

**One fictional deployment, two consumers.** The mock API serves the dataset to
the console; feature 042's demo seeder loads the same dataset into Postgres. Two
datasets would drift, and the first person to notice would be a user whose demo
looked nothing like the screenshots.

**Fixtures live at the root, not inside the console.** They are consumed by
TypeScript, by Python and by both test suites. Putting them under `console/`
would make the Python seeder reach across a boundary the import contracts exist
to police.

## Phases

1. **Contract coverage.** Enumerate every endpoint the console consumes from the
   OpenAPI document; split it into what the gateway serves today and what it will
   serve after features 038, 039 and 044; the coverage test that fails on an
   uncovered one.
2. **Capture.** The command, both sources, the per-record source attribution, the
   raw format, the missed-endpoint report, and the handling that keeps raw
   captures out of the repository.
3. **Anonymisation.** Keyed pseudonym derivation, field allowlist and denylist,
   credential removal, timestamp shifting, distribution preservation,
   determinism.
4. **Verification.** The adversarial identifier scan taking the operator's real
   values from outside the repository; the referential-integrity check; the
   OpenAPI validation.
5. **Scenarios.** The seven named sets, the manifest, per-endpoint overrides, and
   the generated `scale` scenario.
6. **Mock server.** Path and method fidelity, streaming with controllable rate,
   disconnection and replay, injected latency and failure, session-scoped writes,
   the outbound-request refusal.
7. **Handover.** Wire the console development loop and test harness to it; wire
   feature 042's seeder to the same dataset; assert exactly one fictional
   deployment exists.

## Risks

- **A leak that the scan does not catch.** The most serious risk in the feature.
  Mitigated by scanning against the operator's actual values rather than against
  patterns alone, by dropping rather than pseudonymising anything
  credential-shaped, and by never committing the raw capture — so a miss is
  recoverable by re-running the pipeline rather than by rewriting history.
- **Fixtures rot as the API changes.** Mitigated by FR-017 failing the build on a
  contract mismatch and by NFR-004 making re-capture routine.
- **The dataset becomes the only thing the console is ever tested against.** It
  is development and test infrastructure, not a substitute for the end-to-end
  suite in feature 033, which runs against a real gateway and a real database.
