# Tasks — 037 Estate Inventory and Health Model

## Phase 1 — Model and storage

- **T-001** Failing contract test for the estate repository port: write, read,
  update, query, tenant isolation.
- **T-002** Resource model: identity, kind, source, native id, display name,
  parent, typed attributes, labels, owning team node.
- **T-003** Kind registry — declared, extensible by an integration, closed at
  runtime. Test that an unknown kind is rejected at registration, not at write.
- **T-004** Identity derivation from source plus native id; test it survives a
  rename, a restart and a re-discovery.
- **T-005** Postgres implementation, migration, and the fake used by unit tests.
- **T-006** Masking applied to attributes before storage; test a secret-shaped
  and a personal-identifier-shaped attribute.

## Phase 2 — Discovery contract

- **T-007** Discovery protocol in `integrations/_base/`, with rate limits and a
  read side-effect level declared.
- **T-008** Sweep orchestration using the scheduler's lease-based claiming.
- **T-009** Failing test: two replicas sweeping concurrently converge to one
  result.
- **T-010** Incremental and full modes; a source supporting neither falls back
  correctly.
- **T-011** Assert discovery holds no credential and calls only through the
  credential proxy.
- **T-012** Bound the sweep in time and in provider calls; test that exceeding
  the bound suspends and resumes rather than truncating.

## Phase 3 — Absence and staleness

- **T-013** Failing test: a failed sweep marks nothing absent and marks the
  affected resources stale with the reason.
- **T-014** Failing test: a successful sweep marks the gone resource absent with
  a timestamp and retains its history.
- **T-015** Per-kind freshness intervals; a resource past its interval reports
  stale rather than its last known state.
- **T-016** Test that one integration's failure leaves other integrations'
  resources untouched.

## Phase 4 — Reconciliation

- **T-017** Failing test: two sources describing one thing reconcile to one
  resource with both attributed.
- **T-018** Changed parent — a guest migrated between nodes — updates the
  relationship without duplicating the resource.
- **T-019** Provider identity reuse after deletion produces a new resource, not a
  resurrection of the old one.
- **T-020** A source reporting no stable identifier is rejected with a named
  error, not stored under a generated id.

## Phase 5 — Health

- **T-021** Signal recording with named values and timestamps.
- **T-022** Closed health state set; test that no code path can assign a state
  outside it.
- **T-023** Provider status mappings with raw value retained; test an unmapped
  provider status becomes `unknown`, never `healthy`.
- **T-024** Derivation record; failing test asserting every state on every kind
  is explainable and retrievable.
- **T-025** Parent rollup rules, declared and visible on the parent.
- **T-026** Maintenance windows — bounded, distinct from healthy, excluded from
  problem counts, included in the estate.

## Phase 6 — History and query

- **T-027** Transition log with previous state and causing signal.
- **T-028** Query by kind, health, source, label, team, parent, freshness.
- **T-029** Summary rollup; failing benchmark at ten thousand resources.
- **T-030** Links from a resource to the incidents that referenced it and the
  runs that touched it.
- **T-031** Retention under the existing policy; test nothing introduces a second
  retention path.

## Phase 7 — Surfaces

- **T-032** Gateway endpoints: estate query, summary, resource detail,
  maintenance set and clear. Contract tests for each.
- **T-033** CLI commands for the same, with the project's table and JSON output.
- **T-034** Console estate panels from feature 036, against the real endpoints.

## Definition of done

- SC-001 through SC-008 each proven by a named test.
- Ten thousand resources discovered, summarised and queried within budget.
- `make verify` green.
