# Tasks — 032 Mock Data Plane

Test-first throughout. The verification checks in phase 4 are written before the
pipeline in phase 3 that must satisfy them.

## Phase 1 — Contract coverage

- **T-001** Enumerate every endpoint the console consumes from the committed
  OpenAPI document.
- **T-002** Failing coverage test: an endpoint with no fixture fails the suite,
  naming the endpoint.

## Phase 2 — Capture

- **T-003** Split the endpoint list into what the gateway serves today and what
  features 038, 039 and 044 will serve later. The split is data the capture
  reads, not a comment.
- **T-004** Capture command reading the live NinjaSRE gateway for the first set,
  recording the request, the response and the contract version alongside each.
- **T-005** Read-only command allowlist as a declared file. Failing test: a
  command outside it fails the capture rather than running, naming the command.
- **T-006** SSH channel for the second set. Connection details from
  configuration; topology per
  `../044-proxmox-integration/cluster-baseline.md`; the SSH identity supplied at
  run time and never written into the repository.
- **T-007** Prefer `pvesh ... --output-format json` for everything the API
  covers. Failing test: a `pvesh`-derived payload validates against the schema
  feature 044's client will return, so it survives the handover.
- **T-008** Shell reads for what the API cannot answer — failed `systemd` units,
  thin-pool metadata percentage, `corosync.conf`, mount state, boot history.
  Each with a parser and a fixture of its real output.
- **T-009** Projection into the response shapes features 038 and 039 declare.
- **T-010** Per-record provenance — gateway, `pvesh`, or shell. Failing test that
  a projected record cannot be mistaken for one the gateway returned, and that
  the `pvesh` and shell classes are distinguishable from each other.
- **T-011** Ad-hoc query mode: one command, one allowlisted read, answer on
  stdout. Failing test that it refuses a command outside the allowlist.
- **T-012** Recording an ad-hoc answer into the fixture set goes through the same
  anonymisation, provenance and referential check as a captured one. Failing test
  that no second path into the dataset exists.
- **T-013** Missed-endpoint report; the capture states what it could not reach
  and why, per source.
- **T-014** Raw captures excluded from version control, excluded from logs, and
  deleted by the pipeline once anonymised output exists. Test the deletion. The
  infrastructure read carries guest configuration and possibly cloud-init
  secrets — assert none of it reaches a log line.
- **T-015** Run both captures against the reference cluster.

## Phase 3 — Anonymisation

- **T-016** Keyed, deterministic pseudonym derivation; the key supplied at run
  time and never committed.
- **T-017** Failing test: one real value maps to one pseudonym across every file.
- **T-018** Field denylist — tokens, keys, certificates, passwords, cloud-init
  blocks, connection strings, authorisation headers — **removed**, not
  pseudonymised.
- **T-019** Identifier replacement across hostnames, node and guest names,
  addresses, MACs, domains, URLs, e-mail addresses, principals, teams, storage
  and pool names, and free text containing any of them.
- **T-020** Timestamp shift to a fixed reference instant preserving every
  interval. Test that intervals are unchanged.
- **T-021** Failing test: distribution is preserved — resource counts per kind,
  the ratio between kinds, utilisation percentages, payload sizes, node skew.
- **T-022** Failing test: the awkward properties survive — at least one volume
  above 93%, one disabled job, one failed unit set, one unknown datastore, one
  coverage gap.
- **T-023** Failing test: two runs on one capture produce byte-identical output.

## Phase 4 — Verification

- **T-024** Adversarial identifier scan taking the operator's real values from a
  file outside the repository; fails the build on any match. Write this before
  phase 3 is complete and run it against the first output.

  The file must list, at minimum: both node addresses and hostnames, the cluster
  name, every guest name, every storage and pool name, every domain and
  subdomain the deployment answers on, the operator's name and e-mail, and any
  VIP or internal address range. `../044-proxmox-integration/cluster-baseline.md`
  names all of these for the reference cluster and is itself uncommitted; the
  scan reads a file the operator maintains, not that document, so the list can
  hold values too sensitive to write down even there.
- **T-025** Secret-pattern scan over the anonymised output as a second net.
- **T-026** Referential-integrity check; failing test on a seeded broken
  reference, naming it.
- **T-027** OpenAPI validation of every fixture; failing test on a seeded
  contract change, naming endpoint and field.
- **T-028** Plausibility check: events ordered, incidents opened before closed,
  episodes after their runs.

## Phase 5 — Scenarios

- **T-029** Scenario manifest with per-endpoint overrides.
- **T-030** `populated` — a full deployment mid-operation.
- **T-031** `empty` — nothing at all.
- **T-032** `first-run` — configured but incomplete, setup checklist visible.
- **T-033** `degraded` — endpoints slow, refused, 500, 403, 404, truncated.
- **T-034** `incident-live` — a run in flight.
- **T-035** `restricted` — a viewer-role principal for the role matrix.
- **T-036** `scale` — generated from a seed, not committed: ten thousand events,
  ten thousand runs, ten thousand resources, five hundred config nodes.
- **T-037** Failing test: adding a scenario requires no console change.

## Phase 6 — Mock server

- **T-038** Serve every fixture on the gateway's paths, methods and status codes.
- **T-039** Streaming transport with controllable event rate.
- **T-040** Controllable mid-stream disconnection and post-reconnect replay —
  the behaviours feature 037's reducer is proved against.
- **T-041** Injected latency, failure and empty responses, per endpoint.
- **T-042** Session-scoped writes reflected in subsequent reads; reset between
  sessions.
- **T-043** Failing test: any outbound network call from the mock fails loudly.
- **T-044** One command to start it for development; a programmatic entry point
  for tests.
- **T-045** Failing test: serving one scenario twice yields byte-identical
  responses, timestamps included.

## Phase 7 — Handover *(gated on 033 standing the toolchain up)*

- **T-046** Wire the console development loop to the mock.
- **T-047** Wire the console test harness to the mock.
- **T-048** Wire feature 042's demo seeder to this dataset; it defines none of
  its own.
- **T-049** Failing test: exactly one fictional deployment exists in the
  repository.
- **T-050** Scenario load-time and committed dataset size budgets asserted.

## Definition of done

- SC-001 through SC-014 each proven by a named test.
- The identifier scan runs in the gate and is demonstrated to fail on a seeded
  real value.
- No raw capture is committed; no committed file names the real deployment.
- Every console screen renders under `populated`, `empty` and `degraded`.
- `make verify` green.
