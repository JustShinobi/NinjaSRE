# Feature 029 — Chaos and End-to-End Suites

- **Wave:** 7 — Evaluation
- **Branch:** `feat/029-chaos-and-e2e-suites`
- **Status:** Draft
- **Depends on:** 025, 027, 028

## Summary

Synthetic scenarios prove the agent reasons correctly over recorded evidence. These
suites prove it works against **real infrastructure failing for real reasons**:
chaos experiments injected into a live cluster, and an OpenTelemetry demo
application with feature-flag fault injection.

## User scenarios

### Primary story

Before a release, the maintainer runs the chaos suite against a test cluster. Pod
kills, DNS failures, network partitions, and IO latency are injected one at a time;
for each, an investigation runs against genuinely live telemetry and is scored
against the known injected fault. Anything the agent misses becomes a synthetic
scenario for the fast suite.

### Acceptance scenarios

1. **Given** a test cluster and a chaos experiment, **when** the suite runs,
   **then** the fault is injected, an alert fires, an investigation runs, and it is
   scored against the known cause.
2. **Given** the otel-demo application, **when** a feature-flag fault is enabled,
   **then** the resulting failure is investigable end to end through the real
   integrations.
3. **Given** an experiment completes, **when** cleanup runs, **then** the fault is
   removed and the cluster returns to a healthy baseline.
4. **Given** a failed or interrupted run, **when** cleanup runs, **then** no chaos
   experiment is left active.
5. **Given** an e2e run, **when** it completes, **then** it is scored on the same
   axes as a synthetic scenario.
6. **Given** an agent failure on a real fault, **when** it is analysed, **then**
   the recorded telemetry can be turned into a synthetic scenario for the fast
   suite.
7. **Given** no cluster available, **when** the suite is invoked, **then** it skips
   with a clear message rather than failing.
8. **Given** a cloud e2e scenario, **when** it runs, **then** its infrastructure is
   provisioned, exercised, and destroyed, with cost bounded.

### Edge cases

- A chaos experiment that does not produce the intended symptom.
- A cluster that is already unhealthy before injection.
- Cleanup failing and leaving a fault active.
- A cloud e2e run interrupted mid-provisioning, leaking resources.
- Two suites running concurrently against the same cluster.
- Real telemetry containing genuine production-shaped identifiers.

## Requirements

### Functional

**Chaos suite**

- **FR-001** Experiments MUST cover, at minimum: pod kill, container kill,
  CPU stress, memory stress, IO latency, network delay, network partition,
  network corruption, bandwidth limit, DNS failure, DNS random resolution,
  HTTP abort, HTTP delay, and HTTP response fault.
- **FR-002** Each experiment MUST declare the symptom it is expected to produce and
  the root cause the agent should identify.
- **FR-003** Injection MUST be through a supported chaos framework, declaratively
  configured.
- **FR-004** An alert MUST be generated from the injected fault so the pipeline is
  exercised from its real entry point.
- **FR-005** Cleanup MUST run even on failure or interruption, and MUST verify the
  cluster returned to baseline.
- **FR-006** An experiment that does not produce its expected symptom MUST be
  reported as an invalid run, not scored as an agent failure.
- **FR-007** A pre-flight check MUST confirm cluster health before injection.

**otel-demo suite**

- **FR-008** The OpenTelemetry demo application MUST be installable on a cluster
  with its observability stack.
- **FR-009** Faults MUST be injectable through feature flags, covering at minimum:
  cart service failure, product catalogue failure, recommendation cache failure,
  ad service failure, and payment failure.
- **FR-010** Investigations MUST use the real integrations against the demo's real
  telemetry.
- **FR-011** Each fault MUST have a known expected root cause for scoring.

**Cloud e2e**

- **FR-012** Cloud scenarios MUST cover real managed services: EKS, EC2,
  CloudWatch, Lambda, ECS, and RDS.
- **FR-013** Infrastructure MUST be provisioned declaratively and destroyed after
  the run.
- **FR-014** Interrupted runs MUST NOT leak resources; a reaper MUST clean up
  orphans by tag.
- **FR-015** Cost per run MUST be bounded and reported.

**Scoring and feedback**

- **FR-016** Runs MUST be scored on the same axes as synthetic scenarios
  (feature 028).
- **FR-017** A failed run's telemetry MUST be capturable into a synthetic scenario,
  with a documented procedure.
- **FR-018** Results MUST be comparable across releases.

**Operability**

- **FR-019** Suites MUST skip cleanly with a clear message when their
  infrastructure is unavailable.
- **FR-020** Concurrent runs against the same cluster MUST be prevented by a lock.
- **FR-021** Setup and teardown MUST be one command each.
- **FR-022** Real telemetry captured into fixtures MUST be scrubbed of genuine
  identifiers before being committed.

### Key entities

| Entity | Description |
|---|---|
| **ChaosExperiment** | A declarative fault with its expected symptom and cause |
| **FaultInjection** | The otel-demo feature-flag fault configuration |
| **CloudScenario** | Provisioned infrastructure exercised and destroyed |
| **RunValidity** | Whether the experiment produced its intended symptom |
| **CaptureProcedure** | Turning a real failure into a synthetic scenario |

## Success criteria

- **SC-001** All fourteen chaos experiments inject, alert, investigate, score, and
  clean up.
- **SC-002** Cleanup leaves no active fault after a deliberately-interrupted run.
- **SC-003** All five otel-demo faults are investigable end to end.
- **SC-004** Cloud e2e runs provision and destroy with no leaked resources,
  verified by a tag sweep.
- **SC-005** An experiment that fails to produce its symptom is reported invalid
  rather than scored as an agent failure.
- **SC-006** A real failure the agent missed is successfully converted into a
  synthetic scenario that reproduces the miss.
- **SC-007** Suites skip cleanly with no cluster available.
- **SC-008** Cost per cloud e2e run stays within its declared bound.

## Out of scope

- Synthetic scenarios (feature 027)
- Scoring logic (feature 028)
- Production deployment (feature 030)

## Clarifications

| Question | Resolution |
|---|---|
| Why run against real infrastructure when synthetic scenarios are cheaper? | Synthetic fixtures are recorded from a moment in time. Real telemetry is noisier, has more irrelevant signal, and includes failure modes nobody thought to record. The chaos suite finds what the synthetic suite cannot know to test. |
| Is this suite run on every change? | No. Synthetic runs on every pull request; chaos and e2e run before a release and on a schedule. Their value is finding new failure modes, not gating routine changes. |
| What happens when the agent fails a chaos run? | FR-017: the telemetry is captured into a synthetic scenario, so the fast suite covers it permanently. That is the feedback loop from the expensive suite to the cheap one. |
| How is cost controlled for cloud e2e? | Declarative provisioning with destruction (FR-013), a tag-based orphan reaper (FR-014), and a declared per-run bound that is reported (FR-015, SC-008). |
