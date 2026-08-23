# Tasks — 030 Deployment Profiles

## Phase 1 — Validation and startup (test-first)

- **T001** Build a misconfiguration fixture set: missing provider credential, wrong
  encryption key, unreachable database, invalid profile, conflicting sandbox and
  profile settings.
- **T002** Write the test asserting each produces a specific, actionable startup
  error naming setting and problem (SC-006). Red.
- **T003** `platform/startup/validation.py`: configuration checks (FR-006).
- **T004** Key verification before migrations: stored credentials decrypt with the
  configured key (FR-020).
- **T005** `platform/startup/migrations.py`: advisory-locked, ordered application
  (FR-007).
- **T006** Application-to-schema compatibility check, refusing to run on an
  incompatible schema (FR-014).
- **T007** `platform/startup/readiness.py`: per-dependency readiness reporting
  (FR-008).
- **T008** Concurrent-replica startup test: no migration race.

## Phase 2 — Images

- **T009** `deploy/images/app.Dockerfile`: multi-stage, minimal base, non-root.
- **T010** [P] `console.Dockerfile`.
- **T011** [P] `proxy.Dockerfile`.
- **T012** `postgres.Dockerfile` with `pgvector` and Apache AGE, versions pinned
  and compatibility-tested.
- **T013** Digest pinning for all base images.
- **T014** Image vulnerability scan in CI.

## Phase 3 — Compose profiles

- **T015** `deploy/compose/docker-compose.dev.yml`: app plus Postgres, in-process
  proxy, `process` sandbox (FR-002).
- **T016** `deploy/compose/docker-compose.yml`: app, console, Postgres, proxy
  (FR-003); confirm SC-002 four containers.
- **T017** Profile selection by a single configuration value driving sandbox,
  proxy, and concurrency defaults (FR-005).
- **T018** `.env.example` documenting every setting: default, required, effect
  (FR-009).
- **T019** Minimum viable configuration is one provider credential; everything else
  defaults (FR-010).
- **T020** Admin token printed at first start.
- **T021** Golden template application during setup (FR-026).
- **T022** Measure time to first successful investigation on a clean machine
  (SC-001).

## Phase 4 — Helm chart

- **T023** `deploy/helm/ninjasre/`: chart skeleton and `values.yaml`.
- **T024** Application deployment with configurable replicas.
- **T025** [P] Console deployment.
- **T026** [P] Credential proxy deployment.
- **T027** Sandbox pod configuration with Envoy egress control (feature 009).
- **T028** Migration job running before application rollout.
- **T029** [P] External or in-cluster Postgres options.
- **T030** [P] OTel collector configuration.
- **T031** [P] SSO configuration.
- **T032** Leader-claimed scheduler across replicas (feature 016).
- **T033** Chart lint and install test against a Kind cluster.

## Phase 5 — Backup, restore, upgrade

- **T034** `deploy/ops/backup.sh`: single artefact covering relational, vector, and
  graph, plus a manifest recording versions (FR-015).
- **T035** `deploy/ops/restore.sh`: restore with integrity verification (FR-016).
- **T036** Version-checked restore: migrate forward or refuse with a reason
  (FR-017).
- **T037** Automated backup-restore-verify cycle in CI (FR-018); confirm SC-004.
- **T038** Skip-version upgrade applying migrations in order (FR-011); confirm
  SC-003.
- **T039** Failed-migration behaviour: pre-migration state or a documented
  recoverable one (FR-012).
- **T040** Documented and tested rollback path per release (FR-013).

## Phase 6 — Keys and air-gapped

- **T041** Operator-supplied encryption key; never generated silently (FR-019).
- **T042** `deploy/ops/rotate_key.py`: online batch re-encryption (FR-021); confirm
  SC-007 with no downtime and no loss.
- **T043** Key-loss consequences and recovery procedure documented (FR-022).
- **T044** `deploy/images/bundle.sh`: export all images as one archive (FR-023).
- **T045** Local-model configuration path for air-gapped deployment.
- **T046** Configurable trust settings for TLS-intercepting proxies (FR-025).
- **T047** Air-gapped run: full investigation with no internet access (SC-005).

## Phase 7 — Verification

- **T048** Network monitor during a full investigation; assert no outbound
  connection the operator did not configure (FR-024); confirm SC-008.
- **T049** Confirm SC-006: every misconfiguration fixture produces its actionable
  error.
- **T050** Confirm SC-001 on all three host platforms.
- **T051** Operator documentation: profile selection, setup, upgrade, backup,
  key management, air-gapped installation.
- **T052** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] First investigation within fifteen minutes on a clean machine (SC-001)
- [ ] `standard` profile is four containers (SC-002)
- [ ] Skip-version upgrade applies with no data loss (SC-003)
- [ ] Backup and restore preserve relational, vector, and graph integrity (SC-004)
- [ ] Air-gapped deployment runs a full investigation (SC-005)
- [ ] Every misconfiguration produces an actionable error (SC-006)
- [ ] Key rotation with no downtime or loss (SC-007)
- [ ] No unconfigured outbound connections observed (SC-008)
- [ ] `make verify` green
