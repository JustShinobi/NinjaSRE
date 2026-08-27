# Tasks — 041 First Run, Seeding and Demo Mode

## Phase 1 — The regression test, first

- **T-001** Failing end-to-end test: bring up a clean deployment, read the
  credential from where the operator reads it, sign in, reach an authenticated
  page. Confirm it fails against the current bootstrap before changing anything.

## Phase 2 — Bootstrap

- **T-002** Issue the bootstrap credential through the identity system: short
  expiry, one grant, no gateway special case.
- **T-003** Deliver it to a host file and print it with its expiry; make it
  retrievable again without a restart.
- **T-004** Failing test: using the bootstrap credential to establish a durable
  one expires the bootstrap credential.
- **T-005** Sweep asserting the bootstrap credential appears in no log, no audit
  export and no error message.
- **T-006** Idempotent bring-up; failing test that running it twice changes
  nothing.
- **T-007** Migration version check that refuses an incompatible schema with a
  named error rather than guessing.
- **T-008** Confirm T-001 now passes.

## Phase 3 — Self-check

- **T-009** Finding type requiring both a problem and a next action to construct;
  failing test that a bare failure cannot be emitted.
- **T-010** Extend `deploy/ops/preflight.py` with: database and schema version,
  credential proxy, model provider, each configured integration, scheduler,
  observer, disk space, clock skew.
- **T-011** Single-pass reporting ordered by how much each finding blocks.
- **T-012** Entry points from CLI, console and bring-up.
- **T-013** Timeouts; failing test that an unreachable dependency does not hang
  the check.
- **T-014** Coverage test: every finding the check can produce has a problem and
  an action.

## Phase 4 — Model verification

- **T-015** Failing test: an endpoint that answers but cannot tool call fails
  verification with a message naming the limitation.
- **T-016** Exercise tool calling and structured output against the configured
  provider.
- **T-017** Report which of the endpoint's available models do satisfy the
  contract, where the provider can enumerate them.

## Phase 5 — Setup experience

- **T-018** Setup checklist state model; each step verified against the real
  dependency, not against configuration presence.
- **T-019** Console checklist appearing when incomplete, disappearing on
  completion, reachable afterwards.
- **T-020** Guided first investigation running against whatever the operator
  connected, producing a readable transcript.

## Phase 6 — Demo mode

- **T-021** Coherent scenario dataset: estate, topology, incidents, runs with
  transcripts, episodes, strategies with anti-patterns, approvals, audit history.
- **T-022** Failing test: every reference in the demo dataset resolves.
- **T-023** Demonstration label as a schema column on every seeded record.
- **T-024** Fixture transport that raises on any real network call; failing test
  that demo mode makes no external call.
- **T-025** Scripted investigation that streams like a real one, so the live
  transcript is demonstrable without a model.
- **T-026** One-action removal; failing test sweeping every table for residue.
- **T-027** Failing test: demo mode refuses to enable over non-demonstration
  data unless forced.
- **T-028** Generate demo fixtures through the integrations' existing contract
  tests, so an API change breaks both together.

## Phase 7 — Diagnostics and budgets

- **T-029** Bring-up failure messages stating what, why and what to do; reachable
  afterwards from console and CLI.
- **T-030** Support bundle in one command: versions, configuration with secrets
  removed, recent logs, self-check results, schema state. Test the secret
  removal.
- **T-031** Assert the bring-up, demo population and self-check budgets.

## Definition of done

- SC-001 through SC-010 each proven by a named test.
- T-001 passing, and demonstrated to have failed before phase 2.
- `make verify` green.
