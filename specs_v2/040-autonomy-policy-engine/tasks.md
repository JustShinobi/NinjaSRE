# Tasks — 039 Autonomy Policy Engine

## Phase 1 — Risk classes

- **T-001** Closed, ordered risk-class set accounting for reversibility, blast
  radius, data loss and availability loss.
- **T-002** Risk declaration on the capability; validation at registration with a
  named error.
- **T-003** Failing test: a capability with no declared risk class resolves as
  the highest class, never as unclassified.
- **T-004** Classify every capability currently in the catalogue; a coverage test
  fails when a new one lands unclassified.

## Phase 2 — Policy schema

- **T-005** Level set — `propose_only`, `act_on_low_risk`, `act_and_report` —
  closed and ordered.
- **T-006** Scope kinds: deployment, team node, resource kind, label selector,
  individual resource, capability, capability × resource.
- **T-007** Express policies through the hierarchical config service; contract
  test against the real service for merge, locks and approval gating.
- **T-008** Failing test: a malformed policy fails at save time with a named
  error, never at decision time.
- **T-009** Export and import as a reviewable document; round-trip test.

## Phase 3 — Resolution

- **T-010** Failing test: with no configuration, every action of every risk class
  requires approval.
- **T-011** Pure resolver taking action, subjects, policy set and clock.
- **T-012** Precedence with most-specific-wins; deterministic tie-breaking; test
  two rules at equal specificity.
- **T-013** Failing test: an action across resources with different levels
  resolves to the least permissive.
- **T-014** Explanation in the return value: rules considered, applied, winner,
  reason.
- **T-015** Exhaustive matrix test over every level × risk class × scope
  combination.
- **T-016** Benchmark: resolution within budget at a thousand rules.

## Phase 4 — Bounds

- **T-017** Failing test: the kill switch refuses every action at every level and
  no configuration overrides it.
- **T-018** Kill switch taking effect immediately for decisions not yet executed.
- **T-019** Freeze windows with explicit timezones; test across a timezone
  boundary and a daylight-saving change.
- **T-020** Action budgets per resource, capability and team over an interval;
  test a budget interval spanning a restart.
- **T-021** Budget exhaustion downgrades to approval and raises its own attention
  item.
- **T-022** Failing test: an action with no rollback plan requires approval at
  every level.
- **T-023** Refusal attribution — the response names which bound refused.

## Phase 5 — Modes

- **T-024** Dry-run at any scope; failing test using a fake actuator that records
  calls, asserting none were made.
- **T-025** Dry-run records what would have happened, in enough detail to review.
- **T-026** Time-bounded override with automatic expiry; test it expires and is
  audited on expiry.
- **T-027** Policy-change preview against a recorded week of action history;
  test it reports the differences correctly.

## Phase 6 — Enforcement

- **T-028** Failing structural test: an actuator reaching execution without the
  resolver fails the suite. Write this before the resolver is wired to anything.
- **T-029** Single path from proposal to execution.
- **T-030** Migrate every existing actuator in `capabilities/tools/remediation/`
  onto the path.
- **T-031** Audit every decision, permitting and refusing, with the full
  explanation. Test both directions appear.

## Phase 7 — Surfaces

- **T-032** Gateway endpoints: policy read, write, preview, dry-run, kill switch,
  freeze windows, budgets. Contract tests for each.
- **T-033** CLI commands for the same, including a `why` command that explains a
  resolution for a given action and resource.
- **T-034** Console: resolved level and explanation shown on the resource and on
  every proposal before it is acted on.

## Definition of done

- SC-001 through SC-011 each proven by a named test.
- The exhaustive decision matrix passes.
- Every existing actuator migrated; the structural test enforces it.
- `make verify` green.
