# Tasks — 009 Sandbox Profiles

## Phase 1 — Port and contract suite (test-first)

- **T001** `platform/sandbox/port.py`: `Sandbox` protocol — provision, execute,
  stream, interrupt, release. Docstring-only bodies.
- **T002** `platform/sandbox/spec.py`: `SandboxSpec` with CPU, memory, wall clock,
  scratch, process count; `EgressPolicy` derived from `InjectionRule.hosts`.
- **T003** Add sandbox limits to `config/constants/security.py`.
- **T004** Write the shared contract suite: provision, execute a capability,
  stream output, hit each resource limit, interrupt, release (SC-001). Red.
- **T005** Write `tests/security/test_sandbox_isolation.py`: a probe capability
  attempting to read another investigation's filesystem, processes, and network
  (SC-004). Red.
- **T006** Write the egress test: a probe capability targeting an unlisted host
  (SC-002). Red.
- **T007** Write the no-fallback test: force provisioning failure, assert the
  investigation fails (SC-006). Red.
- **T008** `platform/sandbox/selection.py`: deployment-level profile resolution
  (FR-005).

## Phase 2 — Process profile

- **T009** `profiles/process/runner.py`: subprocess execution, streaming,
  interruption.
- **T010** `profiles/process/limits_posix.py`: `resource` limits for CPU, memory,
  process count, plus a wall-clock watchdog.
- **T011** `profiles/process/limits_windows.py`: Job Objects for process count and
  memory; document the CPU-limit gap.
- **T012** Startup reporting of weaker guarantees on Windows (SC-007).
- **T013** Proxy-only routing: capability HTTP traffic reaches only the credential
  proxy.
- **T014** Structured error identifying which limit terminated execution (FR-008).
- **T015** Contract suite green for `process`.

## Phase 3 — Container profile

- **T016** `profiles/container/image.py`: runtime image with capability content
  mounted read-only (FR-020).
- **T017** `profiles/container/network.py`: dedicated bridge with no default route;
  only the proxy reachable.
- **T018** `profiles/container/runner.py`: provision with read-only root and tmpfs
  scratch, execute, stream, interrupt, release (FR-019).
- **T019** Resource limits via container runtime constraints.
- **T020** Contract suite green for `container`.
- **T021** Egress test green for `container`.

## Phase 4 — Kubernetes profile

- **T022** `profiles/kubernetes/pod_spec.py`: pod definition, security context,
  read-only root, scratch volume, resource limits.
- **T023** `profiles/kubernetes/envoy.py`: sidecar configuration generated from
  `EgressPolicy` (FR-011).
- **T024** `NetworkPolicy` denying direct pod egress, forcing traffic through the
  sidecar.
- **T025** `profiles/kubernetes/runner.py`: provision, execute, stream, interrupt,
  release.
- **T026** Interruption propagation into the pod (FR-017).
- **T027** Contract suite green for `kubernetes` (SC-001 complete).
- **T028** Egress test green for `kubernetes` (SC-002 complete).

## Phase 5 — Pool, claims, TTL

- **T029** `profiles/kubernetes/warm_pool.py`: configurable pool, replenishment.
- **T030** `profiles/kubernetes/claims.py`: tenant-scoped claim binding with a
  lease.
- **T031** Single-tenant guarantee: an instance is never reused across tenants
  without a full reset (FR-016); test it.
- **T032** `profiles/kubernetes/ttl.py`: TTL with refresh while the investigation
  is active (FR-014).
- **T033** On-demand provisioning fallback when the pool is exhausted.
- **T034** Measure provisioning latency at the configured pool size (SC-003).

## Phase 6 — Reaper, observability, verification

- **T035** `platform/sandbox/reaper.py`: lease-based, safe across replicas
  (FR-015).
- **T036** Orphan detection for sandboxes whose owning run no longer exists.
- **T037** Confirm SC-005: kill the agent mid-run; one reaper cycle leaves no
  orphans.
- **T038** `platform/sandbox/content.py`: immutable capability and skill delivery;
  test that a sandbox cannot modify what it will execute (FR-020).
- **T039** Sandbox lifecycle events into the run trace (FR-021).
- **T040** Blocked-egress auditing with target, capability, investigation (FR-012).
- **T041** `platform/sandbox/health.py`: pool size, active count, provisioning
  latency, reaper status (FR-022).
- **T042** Confirm SC-004 isolation test green across all three profiles.
- **T043** Confirm SC-006 no-fallback test green.
- **T044** Confirm SC-007 on all three operating systems.
- **T045** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] One contract suite passes on all three profiles (SC-001)
- [ ] Unlisted-host egress refused in all three (SC-002)
- [ ] Warm-pool provisioning within the latency target (SC-003)
- [ ] Concurrent investigations mutually invisible (SC-004)
- [ ] No orphans after one reaper cycle following an agent kill (SC-005)
- [ ] Provisioning failure fails closed (SC-006)
- [ ] `process` profile works on three OSes with Windows gaps reported (SC-007)
- [ ] `make verify` green
