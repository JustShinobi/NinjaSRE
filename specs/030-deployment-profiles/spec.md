# Feature 030 — Deployment Profiles

- **Wave:** 8 — Operations
- **Branch:** `feat/030-deployment-profiles`
- **Status:** Draft
- **Depends on:** 006, 007, 009, 013, 019, 020, 021, 022

## Summary

Three ways to run NinjaSRE — `dev`, `standard`, and `enterprise` — with the
migration, backup, upgrade, and secret-management story each one needs. The
measure of success is simple: a fresh operator reaches their first successful
investigation in under fifteen minutes, and nothing they run phones home.

## User scenarios

### Primary story

A platform engineer clones the repository, copies the example environment file,
adds one API key, and runs one command. Four containers start, migrations apply,
and the console is reachable with an admin token printed in the terminal. Their
first investigation runs eleven minutes after they started.

### Acceptance scenarios

1. **Given** a clean machine with a container runtime, **when** the `standard`
   profile starts, **then** all services come up healthy and migrations apply
   automatically.
2. **Given** a running deployment, **when** an upgrade is applied, **then**
   migrations run under a lock, no data is lost, and a rollback path exists.
3. **Given** a deployment, **when** backup runs, **then** a single artefact
   captures all state and restores into a clean instance with integrity intact.
4. **Given** the `dev` profile, **when** it starts, **then** it requires only
   Postgres and the application — the credential proxy runs in-process.
5. **Given** the `enterprise` profile, **when** it is deployed to Kubernetes,
   **then** agent replicas, sandbox pods with egress control, Postgres, and
   optional SSO are all configured.
6. **Given** any profile, **when** it runs, **then** no component makes an outbound
   connection the operator did not configure.
7. **Given** a misconfiguration, **when** startup runs, **then** it fails with a
   specific, actionable message rather than a generic error.
8. **Given** an encryption key change, **when** it is applied, **then** stored
   credentials are re-encrypted with no downtime and no loss.

### Edge cases

- An upgrade skipping several versions.
- A migration failing partway.
- Restoring a backup taken on a different version.
- A deployment with no internet access at all, including for images.
- An encryption key lost entirely.
- Concurrent replicas racing on startup migration.
- Running behind a corporate proxy with TLS interception.

## Requirements

### Functional

**Profiles**

- **FR-001** Three profiles MUST exist: `dev`, `standard`, `enterprise`.
- **FR-002** `dev` MUST require only Postgres plus the application, with the
  credential proxy in-process and the `process` sandbox profile.
- **FR-003** `standard` MUST be a Compose deployment of: application, console,
  Postgres, and credential proxy — four containers.
- **FR-004** `enterprise` MUST be a Helm chart supporting: agent replicas, sandbox
  pods with Envoy egress control, Postgres (external or in-cluster), OTel export,
  and SSO.
- **FR-005** A profile MUST be selectable by a single configuration value, and MUST
  determine the sandbox profile, proxy deployment, and concurrency defaults
  consistently.

**Startup and configuration**

- **FR-006** Startup MUST validate configuration and fail with specific,
  actionable messages naming the setting and the problem.
- **FR-007** Migrations MUST apply automatically at startup under an advisory lock
  so concurrent replicas do not race.
- **FR-008** Health and readiness MUST gate traffic, and readiness MUST report
  which dependency is not ready.
- **FR-009** A `.env.example` MUST document every setting with its default, whether
  it is required, and what it affects.
- **FR-010** The minimum viable configuration MUST be one LLM provider credential;
  everything else MUST have a working default.

**Upgrade and rollback**

- **FR-011** Upgrades MUST support skipping versions, applying migrations in order.
- **FR-012** A failed migration MUST leave the database in its pre-migration state
  or in a documented recoverable state, never an ambiguous one.
- **FR-013** A rollback path MUST be documented and tested for each release.
- **FR-014** Version compatibility between application and schema MUST be checked
  at startup, refusing to run against an incompatible schema.

**Backup and restore**

- **FR-015** A single backup command MUST capture all state: relational, vector,
  and graph.
- **FR-016** Restore MUST bring up a working instance from a backup with integrity
  verified.
- **FR-017** Restoring a backup from a different version MUST be detected and
  either migrated forward or refused with a clear reason.
- **FR-018** Backup and restore MUST be exercised by an automated test.

**Secrets and keys**

- **FR-019** The encryption key MUST be supplied by the operator and MUST NOT be
  generated silently.
- **FR-020** Startup MUST verify stored credentials are decryptable and fail early
  if not.
- **FR-021** Key rotation MUST re-encrypt stored credentials without downtime.
- **FR-022** Key loss MUST be documented with its consequences and the recovery
  procedure.

**Air-gapped operation**

- **FR-023** A fully offline deployment MUST be supported, including image
  distribution and a local model.
- **FR-024** No component may require an outbound connection the operator did not
  configure.
- **FR-025** Operation behind a proxy with TLS interception MUST be supported
  through configurable trust settings.

**Templates**

- **FR-026** The golden configuration templates from feature 013 MUST be applicable
  during initial setup.

### Key entities

| Entity | Description |
|---|---|
| **DeploymentProfile** | `dev`, `standard`, or `enterprise` with its component set |
| **StartupValidator** | Configuration checks producing actionable failures |
| **MigrationRunner** | Locked, ordered, version-checked schema application |
| **BackupArtefact** | A single restorable capture of all state |
| **KeyRotation** | Zero-downtime credential re-encryption |

## Success criteria

- **SC-001** A fresh operator reaches their first successful investigation in under
  fifteen minutes on the `standard` profile.
- **SC-002** The `standard` profile is four containers.
- **SC-003** An upgrade skipping two versions applies cleanly with no data loss.
- **SC-004** Backup and restore into a clean instance preserves relational, vector,
  and graph integrity.
- **SC-005** A fully air-gapped deployment with a local model runs a complete
  investigation.
- **SC-006** Every misconfiguration in a fixture set produces a specific,
  actionable startup error.
- **SC-007** Key rotation completes with no downtime and no credential loss.
- **SC-008** A network monitor during a full run observes no outbound connection
  the operator did not configure.

## Out of scope

- Application features
- Managed hosting — there is none
- Autoscaling policy beyond replica configuration

## Clarifications

| Question | Resolution |
|---|---|
| Why is fifteen minutes the target? | It is roughly the attention span an evaluating engineer gives an unfamiliar self-hosted tool. Beyond it, most evaluations end before the tool has demonstrated anything. |
| Why not generate an encryption key automatically? | A silently-generated key ends up in a container layer or a compose file, and the operator does not know it exists until they need to restore a backup on another host. Requiring it makes key management a conscious decision. |
| Is air-gapped operation realistic given LLM dependence? | Yes, and it is why provider neutrality is constitutional. With a local model, a no-egress deployment is fully functional (SC-005). |
| Why verify no unexpected outbound connections? | Constitution Article X. SC-008 makes it an observed property rather than a claim, which is exactly what a security review will ask for. |
