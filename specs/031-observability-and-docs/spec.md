# Feature 031 — Observability and Documentation

- **Wave:** 8 — Operations
- **Branch:** `feat/031-observability-and-docs`
- **Status:** Draft
- **Depends on:** 016, 019, 021, 025, 028, 030

## Summary

How an operator understands what NinjaSRE is doing, what it costs, and how to use
it — with nothing leaving their infrastructure. OpenTelemetry pointed at their own
collector and disabled by default, structured local logs, cost visibility, and a
documentation site generated from the same sources the code uses.

## User scenarios

### Primary story

A platform team runs NinjaSRE for a month. Their Grafana shows investigation
volume, median duration, token spend by team and model, capability failure rates,
and integration health — all from OTel data that never left their cluster. When
someone asks what a capability does, the answer is in a docs site generated from
the capability's own metadata, so it cannot be stale.

### Acceptance scenarios

1. **Given** a default deployment, **when** it runs, **then** no telemetry is
   exported anywhere.
2. **Given** an operator configures an OTel collector endpoint, **when**
   investigations run, **then** traces, metrics, and logs export there.
3. **Given** exported metrics, **when** they are viewed, **then** they cover
   investigation volume and duration, token and cost by team and model, capability
   invocation and failure rates, integration health, queue depth, and approval
   latency.
4. **Given** a log line, **when** it is emitted, **then** it is structured, carries
   the correlation identifier, and has passed the guardrail engine.
5. **Given** the docs site, **when** the capability catalogue changes, **then** the
   reference pages regenerate and a drift check fails if they were not.
6. **Given** a new operator, **when** they follow the quickstart, **then** they
   reach a successful investigation without consulting anything else.
7. **Given** the dependency scan, **when** it runs, **then** no telemetry or
   analytics package appears in the runtime dependency set.
8. **Given** cost data, **when** it is aggregated, **then** it is attributable per
   team, per run, and per model.

### Edge cases

- An OTel collector that becomes unavailable mid-run.
- Very high cardinality in metric labels.
- A log line containing content the guardrails must redact.
- Documentation referencing a capability that was removed.
- A correlation identifier crossing a sub-agent boundary.
- Cost attribution for a run spanning a model switch.

## Requirements

### Functional

**Telemetry**

- **FR-001** Observability MUST use OpenTelemetry and MUST be **disabled by
  default**.
- **FR-002** When enabled, it MUST export only to an operator-configured endpoint.
- **FR-003** No first-party telemetry, analytics, or crash reporting may exist in
  the runtime dependency set; a CI check MUST enforce this.
- **FR-004** A collector that becomes unavailable MUST NOT affect investigations;
  export failures are dropped with a local counter.
- **FR-005** Metric label cardinality MUST be bounded so a high-cardinality field
  cannot exhaust a collector.

**Metrics**

- **FR-006** Metrics MUST cover: investigation count and duration, outcome
  distribution, token usage and cost by team and model, capability invocation
  counts and failure rates, integration health, scheduler queue depth, approval
  latency, guardrail action counts, and memory recall rates.
- **FR-007** Cost MUST be attributable per team, per run, and per model, including
  runs that switch models mid-flight.
- **FR-008** A reference dashboard definition MUST be shipped for the common
  observability stacks.

**Tracing**

- **FR-009** Distributed traces MUST span the pipeline stages, the runtime loop,
  capability invocations, sub-agent dispatches, and storage access.
- **FR-010** The correlation identifier MUST propagate across sub-agent boundaries
  and into external calls where the protocol allows.

**Logging**

- **FR-011** Logs MUST be structured with a consistent field set.
- **FR-012** Every log line MUST carry the correlation identifier where one exists.
- **FR-013** Logs MUST pass the guardrail engine before emission.
- **FR-014** Log level MUST be configurable per module without a restart.

**Documentation**

- **FR-015** A documentation site MUST cover: quickstart, deployment profiles,
  configuration reference, capability catalogue, integration catalogue, security
  model, evaluation methodology, and contribution guide.
- **FR-016** Capability and integration reference pages MUST be **generated** from
  their metadata; a drift check MUST fail if the generated output is stale.
- **FR-017** The configuration reference MUST be generated from the config schema.
- **FR-018** The quickstart MUST be executable end to end by a new operator with no
  other documentation.
- **FR-019** Documentation MUST be buildable and servable offline.
- **FR-020** Every code example MUST be tested so it cannot rot.
- **FR-021** The security model MUST document the credential proxy, masking,
  guardrails, sandbox profiles, and the approval model, with the threat each
  addresses.
- **FR-022** The evaluation methodology MUST be documented in enough detail for a
  third party to reproduce the published numbers.

**Operational visibility**

- **FR-023** A cost report MUST be available per team and per period from the CLI
  and the console.
- **FR-024** Integration health MUST be visible without opening a dashboard.
- **FR-025** A diagnostic bundle command MUST produce a redacted archive the
  operator can review before sharing.

### Key entities

| Entity | Description |
|---|---|
| **TelemetryConfig** | Operator-configured export target; disabled by default |
| **MetricSet** | The bounded-cardinality metric definitions |
| **TraceSpan** | Pipeline, loop, capability, sub-agent, and storage spans |
| **StructuredLog** | Guardrail-filtered, correlation-carrying log record |
| **GeneratedReference** | Documentation produced from code metadata |
| **DiagnosticBundle** | The redacted local archive |

## Success criteria

- **SC-001** A default deployment exports nothing — verified by network monitoring.
- **SC-002** With a collector configured, all metric families and trace spans
  appear.
- **SC-003** A collector outage does not affect investigations.
- **SC-004** Metric cardinality stays within bounds under a synthetic
  high-cardinality load.
- **SC-005** The documentation drift check fails when a capability changes and docs
  are not regenerated.
- **SC-006** A new operator completes the quickstart to a successful investigation
  using only the quickstart.
- **SC-007** Every documented code example passes its test.
- **SC-008** The dependency scan finds no telemetry or analytics package.
- **SC-009** Cost attribution is correct for a run that switches models mid-flight.

## Out of scope

- Deployment packaging (feature 030)
- Run trace persistence (feature 016) — this feature exports, it does not store
- Marketing site content

## Clarifications

| Question | Resolution |
|---|---|
| Why is observability disabled by default? | Constitution Article X, and practicality: an operator without a collector should not see export errors in their logs on first run. Enabling it is one setting. |
| Why generate reference documentation? | Hand-written capability documentation is stale within two releases. Generation plus a drift check (FR-016, SC-005) means the reference cannot lie. |
| Why document the evaluation methodology in reproducible detail? | Because the product's central claim is a measured one. A number nobody outside the project can reproduce is a marketing claim, not evidence. |
| What is in a diagnostic bundle? | Configuration with secrets removed, recent structured logs, health output, and version information — reviewable by the operator before they share it, since there is no telemetry to send it automatically. |
