# Architecture Robustness and Scalability Improvements

## Context

NinjaSRE already has a strong architectural foundation: a self-hosted modular monolith,
enforced package boundaries, a canonical bounded ReAct runtime, a mandatory credential
proxy for integrations, and a single PostgreSQL datastore serving relational, vector, and
graph workloads.

The most valuable next step is not a migration to microservices. It is closing the gaps
between the current process-oriented runtime and the multi-replica, failure-tolerant
deployment model the platform targets.

This plan preserves the existing architectural principles, including the canonical runtime,
single datastore, provider neutrality, bounded autonomy, and read-only-by-default behavior.

## Objectives

- Make investigations survive process restarts, rolling deployments, and worker failures.
- Make operational safety controls correct across multiple replicas.
- Prevent outbound reports and post-run work from being lost or duplicated.
- Keep provider credentials outside the agent execution process.
- Make production composition deterministic and validated before accepting work.
- Reduce coupling between domain/runtime code and infrastructure services.
- Scale PostgreSQL workloads before introducing additional stateful systems.

## Priority Summary

| Priority | Change | Primary benefit |
|---|---|---|
| P0 | Durable investigation execution | Runs survive restarts and replica changes |
| P0 | Distributed, persistent controls | Correct kill switch, rate limits, and idempotency in HA |
| P0 | Transactional outbox for delivery and post-run work | No lost or accidental duplicate delivery |
| P0 | LLM egress through the credential proxy | Agent processes never hold provider secrets |
| P1 | Canonical production composition root | Predictable startup and runtime configuration |
| P1 | Remove `core -> platform` dependencies | Clearer ports-and-adapters boundary |
| P2 | PostgreSQL workload isolation and partitioning | Higher scale without another datastore |

## 1. Durable Investigation Execution

### Problem

The HTTP gateway currently starts an investigation with `asyncio.create_task`, and the
gateway tracks those tasks in process memory. Pause, cancel, and sub-agent ownership signals
also live inside one `ReActLoop` instance.

This is safe for a single healthy process but is insufficient when:

- a process restarts during an investigation;
- a rolling deployment replaces a replica;
- a worker dies after an external call;
- a cancel or takeover request reaches a different replica;
- two workers attempt to resume the same session.

### Proposed architecture

Introduce durable run work and leasing in PostgreSQL, based on the existing scheduler claim
model:

```text
POST /investigations
        |
        +-- transaction: create run + enqueue investigation work
        v
Worker atomically claims a lease
        |
        +-- heartbeat while active
        +-- checkpoint after every completed iteration and tool result
        +-- consume durable control commands at safe points
        `-- complete, suspend, or release the lease
```

Add ports such as:

- `InvestigationDispatcher`: enqueue and atomically claim run work;
- `RunLease`: claim identity, owner, expiry, and heartbeat;
- `RunCommandStore`: ordered cancel, pause, takeover, resume, and message commands;
- `RunCheckpointStore`: resumable runtime state with optimistic concurrency.

### Required semantics

- Use at-least-once execution with idempotent effects, not an unprovable exactly-once claim.
- Persist a tool result before beginning the next model turn.
- Stop a worker when it loses its lease.
- Use optimistic versioning so only one worker advances a session.
- Make control commands ordered and idempotent.
- Recover expired leases automatically and record the interruption reason.
- Keep the existing safe-point behavior: do not interrupt a capability call halfway through.

### Verification

- Kill a worker after each significant transition and prove the run resumes correctly.
- Send cancel, pause, and messages to a replica that does not own the run.
- Race two workers for the same run and prove only one advances it.
- Run rolling-deployment tests with active investigations.

## 2. Distributed and Persistent Safety Controls

### Problem

Several controls are currently process-local:

- remediation kill switch;
- API rate limiting;
- webhook idempotency;
- alert deduplication;
- live-event broker;
- background-run ownership.

In a multi-replica deployment, changing one replica does not necessarily affect the others.
The kill switch is the highest-risk example: a switch engaged on one process must prevent a
write on every process.

### Proposed architecture

Use PostgreSQL as the authoritative state for correctness-sensitive controls:

- Persist kill-switch state by organisation and team.
- Check the durable kill-switch version within the transaction that authorises a write.
- Fail closed when the current switch state cannot be verified.
- Store webhook idempotency keys with a unique constraint and expiry.
- Store alert fingerprints when cross-replica deduplication is required.
- Use a distributed rate-limit implementation for multi-replica profiles.
- Implement the existing `StreamBridge` port with PostgreSQL `LISTEN`/`NOTIFY`.

Local caches remain valid as optimisations, but not as the source of truth. Invalidation can
use `LISTEN`/`NOTIFY`, while every irreversible write still performs an authoritative check.

### Deployment policy

- `dev`: in-memory implementations remain acceptable.
- `standard`: durable kill switch and webhook idempotency are mandatory.
- `enterprise`: all correctness-sensitive controls use distributed implementations.

### Verification

- Engage the kill switch through one replica and attempt writes through every other replica.
- Deliver the same webhook concurrently to multiple replicas and prove one ingestion effect.
- Restart replicas during rate-limit and deduplication windows.
- Disconnect the stream bridge and prove cursor-based replay remains correct.

## 3. Transactional Outbox and Durable Delivery Ledger

### Problem

The pipeline can deliver directly to destinations, while separate reporting and transit
subsystems provide their own retry and idempotency behavior. This creates multiple outbound
delivery paths with different guarantees.

Direct delivery also creates the classic failure window:

1. the external destination accepts a report;
2. the application process dies;
3. the local delivery result is not committed;
4. recovery sends the report again.

An in-memory delivery ledger does not protect against restarts or other replicas.

### Proposed architecture

Consolidate outbound report delivery behind one durable dispatcher and use a transactional
outbox:

```text
Investigation transaction
    +-- persist diagnosis and outcome
    +-- persist trace state
    `-- insert outbox rows for destinations and post-run work
                           |
                           v
                 Worker claims outbox lease
                           |
                   retry + idempotency
```

Each delivery record should include:

- a stable key derived from `run_id` and destination identity;
- state: pending, delivering, delivered, refused, or failed;
- attempt count and next-attempt time;
- lease owner and expiry;
- destination reference;
- bounded, redacted failure information.

Add a unique database constraint for the stable delivery key. Pass that same key to external
destinations that support idempotency.

### Scope

The same outbox mechanism can handle non-critical-path work:

- report delivery;
- episode extraction;
- embedding generation;
- topology updates;
- strategy synthesis;
- notifications.

This shortens investigation completion latency while preserving an auditable record of what
remains pending or failed.

### Verification

- Crash before and after every delivery transition.
- Simulate a destination accepting a request and timing out before acknowledging it.
- Retry from a different replica.
- Prove one durable delivery record exists per run and destination.

## 4. Route LLM Traffic Through the Credential Proxy

### Problem

Integration clients already follow the intended trust boundary: they carry tenant-scoped
context and the proxy injects credentials at the network edge. LLM transports can still
resolve provider credentials from the agent process environment and pass them to vendor SDKs
inside that process.

This weakens the invariant that secrets never reach the agent execution context.

### Proposed architecture

Add an internal LLM egress transport:

```text
Agent runtime
    |
    +-- mask identifiers
    v
LLM egress proxy
    +-- resolve tenant/team/provider credential
    +-- inject authentication or sign the request
    +-- enforce provider host allow-list
    +-- audit bounded metadata
    `-- forward to provider
```

For providers requiring request signing, such as Bedrock, signing must occur proxy-side. For
cloud deployments, prefer workload identity over long-lived static keys.

### Deployment policy

- Allow environment credentials only in the explicit `dev` profile.
- Refuse or fail readiness when `standard` or `enterprise` exposes provider secrets to the
  application process.
- Preserve local Ollama/vLLM operation without credentials.
- Keep provider SDKs optional and confined to the trusted egress process when used.

### Verification

- Inspect agent environment, trace, prompts, tool arguments, and filesystem for credentials.
- Attempt to make the proxy reach an undeclared host.
- Verify masking before the request crosses the trust boundary.
- Exercise every supported provider through the proxy preflight suite.

## 5. Canonical Production Composition Root

### Problem

The gateway currently accepts a `module:factory` reference for its investigation runner. If
none is configured, most routes remain available and attempts to investigate fail only after
work has been accepted.

This makes deployment composition flexible but leaves the primary product workflow dependent
on external wiring that the shipped application does not own.

### Proposed architecture

Provide a first-party production composition root that deterministically assembles:

- effective tenant and team configuration;
- the selected LLM provider and measured model limits;
- the credential-proxy transport;
- capability and skill catalogues;
- capability selection and tool-schema limits;
- mandatory investigation hooks;
- session/checkpoint storage;
- pipeline delivery and end hooks;
- streaming and trace recorders.

Keep `module:factory` as an explicitly experimental extension point rather than the default
production path.

At startup and readiness time, verify that the deployment can compose the runtime it claims
to provide. Do not return `202 Accepted` for new investigations when no runnable composition
exists.

Record a composition fingerprint on every run, covering at least:

- runtime version;
- model provider and model;
- prompt versions;
- selected capability declaration versions;
- effective guardrail version;
- relevant configuration revision.

### Verification

- Boot each deployment profile from documented configuration alone.
- Prove startup or readiness names every missing dependency.
- Replay a stored composition fingerprint and identify configuration drift.

## 6. Make `core` Independent of `platform`

### Problem

The tier model allows `core` and `platform` to import one another. In practice, this creates a
large bidirectional dependency surface. Many `core -> platform` imports exist only for logging
and metrics, while others expose infrastructure credential schemas to core modules.

Bidirectional package dependencies make ownership less clear and increase the blast radius of
changes.

### Target dependency direction

```text
core
 +-- domain models
 +-- runtime and pipeline
 `-- ports
       ^
       | implements
platform

gateway / surfaces compose both
```

### Migration sequence

1. Replace `core` imports of platform logging with standard-library logging or injected hooks.
2. Move metrics emission behind lifecycle/telemetry ports defined in `core`.
3. Define provider onboarding contracts independently of platform credential storage models.
4. Make memory, masking, guardrails, and persistence implement core-owned ports.
5. Change the import-linter contract to forbid `core -> platform`.

Do this incrementally with characterization tests before each behavior-preserving refactor.

### Verification

- Import and test `core` without importing `platform`.
- Add an import-linter contract forbidding `core -> platform`.
- Run canonical runtime and pipeline tests against pure fakes.

## 7. Scale the Existing PostgreSQL Architecture

### Direction

Keep PostgreSQL, pgvector, and Apache AGE as the single datastore until measurements prove a
specific workload cannot meet its service-level objective. Adding Redis, a separate vector
database, or a graph database would create new backup, security, migration, and consistency
burdens.

### Proposed improvements

- Partition high-volume append-only tables by time, particularly trace events, tool calls,
  evidence, audit events, and observation signals.
- Perform retention by dropping partitions rather than issuing large delete batches.
- Use separate connection pools and budgets for API requests, workers, and the credential
  proxy.
- Apply workload-specific statement timeouts for interactive, vector, and graph queries.
- Bound investigation concurrency per organisation and per team.
- Add an optional read replica for console history and reporting queries.
- Tune pgvector index parameters from measured recall and latency rather than defaults.
- Monitor JSONB payload size, table and index bloat, autovacuum lag, connection saturation,
  vector recall, and graph traversal latency.

### Verification

- Load-test realistic trace and evidence volumes.
- Measure interactive API latency while embeddings and graph reconciliation run.
- Exercise backup, restore, and retention against partitioned tables.
- Establish thresholds that would justify separating a workload in the future.

## Changes Not Recommended Yet

### Do not migrate to microservices

The current modular monolith provides strong boundaries without introducing distributed
transactions, network failure modes, and multiple deployment lifecycles. Separate only the
processes required by security or workload isolation.

### Do not add Redis solely for coordination

PostgreSQL leases, unique constraints, advisory coordination, and `LISTEN`/`NOTIFY` are
sufficient for the current scale and preserve the single-datastore principle.

### Do not replace deterministic capability ranking prematurely

The current catalogue size is small enough for deterministic in-memory scoring. Consider
hierarchical or semantic preselection only when protocol bridges or plugins raise the active
catalogue into the thousands of tools and measurements show selection cost or quality issues.

### Do not split vector or graph storage without evidence

First isolate pools, tune indexes, partition append-heavy data, and measure contention. A new
datastore should answer a demonstrated bottleneck, not an anticipated one.

## Recommended Delivery Sequence

### Phase 1: Durable execution

1. Add run claims, leases, checkpoints, and durable commands.
2. Replace request-owned background tasks with worker-owned claimed work.
3. Add crash and multi-replica recovery tests.

### Phase 2: Distributed safety

1. Persist the kill switch and make write gates fail closed.
2. Make webhook idempotency atomic in PostgreSQL.
3. Implement the cross-replica stream bridge.
4. Add distributed rate limiting for multi-replica profiles.

### Phase 3: Reliable side effects

1. Add the transactional outbox and durable delivery ledger.
2. Consolidate report and transit delivery paths.
3. Move post-run work to leased workers.

### Phase 4: Trust boundary completion

1. Add the LLM egress proxy transport.
2. Move provider credential resolution and request signing to the proxy.
3. Enforce profile-specific credential policy at startup.

### Phase 5: Structural simplification

1. Ship the canonical first-party composition root.
2. Add composition fingerprints and strict readiness.
3. Remove `core -> platform` imports incrementally.

### Phase 6: Measured database scaling

1. Establish load baselines and service-level objectives.
2. Partition high-volume tables and isolate connection pools.
3. Tune vector and graph workloads from production-like measurements.

## Expected Outcome

The first three phases deliver the largest architectural improvement. They move NinjaSRE
from a system that behaves correctly in one healthy process to one that preserves its safety,
evidence, and delivery guarantees during crashes, restarts, rolling deployments, and
multi-replica operation, without abandoning the operational simplicity of the modular
monolith and single-datastore design.
