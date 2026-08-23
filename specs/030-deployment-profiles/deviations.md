# Deviations — 030 Deployment Profiles

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. The composition root the images run had to be written, and is not in tasks.md

T009–T011 ask for Dockerfiles. A Dockerfile needs an entrypoint, and there was
none: `create_app` takes a `GatewayState` somebody built, and feature 020's own
deviations record that composing one "is a deployment concern (feature 030)" —
but no task in *this* feature's list writes it either. Shipping a Dockerfile
whose entrypoint does not exist would be shipping a decoration.

So this feature adds three composition modules that tasks.md does not enumerate:

- **`gateway/http/asgi.py`** — builds `GatewayState` from the environment: the
  PostgreSQL gateway and the token service, both real.
- **`gateway/http/serve.py`** — the process the container runs. Boot sequence
  first, then uvicorn, **on one event loop**, because asyncpg binds a pooled
  connection to the loop that created it and `asyncio.run(boot)` followed by a
  server that starts a second loop produces a deployment that starts perfectly
  and fails on its first query.
- **`gateway/proxy/`** — the credential proxy as a deployable service:
  composition (which must be tier 1, since filling the injection-rule registry
  means reading `integrations/`), and `HttpOutboundSender`, which is the
  production `OutboundSender` feature 007 declared as a port and never
  implemented outside test doubles.

**What is still not composed, and why.** What drives a ReAct loop for a
route-triggered investigation is named by the operator through
`NINJASRE_INVESTIGATOR` (`module:factory`) — the same convention the Makefile
already uses for the chaos and end-to-end suites (`INVESTIGATOR=your.deployment:build`)
and for the same stated reason: composing a runtime means choosing a provider, a
capability catalogue, and a credential proxy, and guessing those from ambient
configuration is how a deployment investigates with a model nobody chose.
Unset, the gateway starts and every route works except starting an
investigation, which refuses with `InvestigatorNotConfigured` naming the
setting.

**The consequence for SC-001, stated plainly:** on a deployment that has not set
`NINJASRE_INVESTIGATOR`, the final step of the fifteen-minute path — "send the
sample alert and read the answer" — does not complete. Everything before it
does. Building that factory is a larger piece of work than any task in this
feature describes, and it is the one thing in the definition of done that this
feature does not close; see §7.

## 2. `platform/startup/` owns policy; the storage layer owns the driver

`tools/check_raw_sql.py` rejects a database driver imported outside
`platform/persistence/`, which means the plan's `platform/startup/migrations.py`
cannot call Alembic. That is the right constraint and it improved the design:

- `platform/startup/migrations.py` holds the **port** (`SchemaMigrator`) and the
  decisions — ordering, skip handling, compatibility, what a failure means.
- `platform/persistence/postgres/migrations.py` gains `AlembicSchemaMigrator`,
  the adapter, structurally satisfying the port without importing it.

The same split put `VaultReEncryptor` in `platform/persistence/rotation.py`
rather than beside the rotation policy: re-encrypting a credential means calling
`reveal`, and `make check-credentials` allows that in the storage layer, the
proxy, and `tests/contract/persistence/` only.

## 3. A real reporting bug the concurrent-replica test found

`apply_at_startup` originally computed what it had applied from the revision it
read *before* acquiring the lock. Four replicas starting together therefore each
reported migrating four revisions, when one had migrated and three had waited.
The test (T008) caught it, and the fix changed the port: `upgrade_to_head`
returns a `MigrationOutcome` rather than a revision string, because only the
lock holder can honestly say what it applied. This is why the port has the shape
it has rather than the simpler one.

## 4. `KeyRing` grew a previous key, which the plan does not mention

FR-021 asks for rotation with no downtime. That is impossible with a single-key
ring: an AES-GCM envelope carries no key identifier, so a row is readable by
exactly the key that wrote it, and a rotation would make every row it had not
reached unreadable while it ran. `KeyRing.configure_previous` installs a
**read-only** fallback for the duration of a rotation — writes always use the
current key, so a half-finished rotation cannot go backwards.

`unseal` now tries the current key and then the fallback. Behaviour with no
fallback installed is unchanged, and
`tests/unit/platform/persistence/test_crypto_key_rotation.py` is what the
no-downtime claim now rests on.

## 5. Digest pinning ships as a mechanism, not as literal digests (T013)

A digest resolves against a registry. Writing one by hand produces a build that
either pulls nothing or pulls something nobody verified, and this session has no
network to resolve one against. What ships instead:

- `deploy/images/base-images.env` — every base image named exactly once, at an
  exact version, never `latest`;
- `deploy/images/pin.sh` — resolves each to a digest against the registry the
  operator actually pulls from, and `--check` fails when anything is unpinned;
- a contract test asserting that no `FROM` names an image inline, that every
  `ARG BASE_*` default matches `base-images.env`, and that no reference floats
  on a moving or version-less tag.

An operator or a release pipeline runs `pin.sh` once and commits the result. The
enforcement is real; the digests are theirs.

## 6. `.env.example` is generated, and completeness is enforced (T018)

The plan asks for a file documenting every setting. A hand-written one is
correct on the day it is written. So `platform/startup/settings.py` is the
catalogue, `tools/generate_env_example.py` renders it, `make check-env-example`
is in `verify`, and a contract test asserts that every `NINJASRE_*` constant the
tier declares is either catalogued or explicitly listed in
`NOT_A_DEPLOYMENT_SETTING` with a reason.

That check found three undocumented settings on its first run
(`NINJASRE_INVESTIGATOR`, `NINJASRE_CHAOS_KUBECONFIG`, `NINJASRE_E2E_ARTIFACTS`)
which is the whole argument for having it.

## 7. Definition of done, item by item

| Item | State |
|---|---|
| SC-001 first investigation in fifteen minutes | **Partly.** The path is modelled with a budget per step and asserted to fit for all three profiles; the deterministic legs are measured by the pre-existing `tools/measure_first_investigation.py` in CI. The final leg needs an investigator factory — see §1. |
| SC-002 `standard` is four containers | **Done.** Asserted against the Compose file *and* against `topology_for`, so the two cannot drift. |
| SC-003 skip-version upgrade, no data loss | **Done.** `pending_revisions`/`apply_at_startup` tested across an empty database, a one-revision gap, a two-revision skip, and a failure part-way that resumes. |
| SC-004 backup and restore preserve all three shapes | **Done offline, and in a CI job with a database.** The manifest, the version decision, and the row-count integrity check are unit-tested; `test-infra/backup/cycle.sh` runs the real cycle against PostgreSQL with both extensions and asserts a truncated archive is refused. It skips with a message where there is no container runtime. |
| SC-005 air-gapped full investigation | **Done.** A complete investigation runs under a socket monitor and opens no socket at all; the air-gapped configuration is asserted to imply no destination off the host. |
| SC-006 every misconfiguration is actionable | **Done.** Eleven fixtures, each asserting the failure names its setting *and* that the remedy says what to type. |
| SC-007 key rotation, no downtime, no loss | **Done.** Readability is asserted between batches against the real ports, and the two-key ring it depends on is tested at the crypto level. |
| SC-008 no unconfigured outbound connection | **Done.** Observed at `socket.socket.connect`, below every client library, during a real investigation. |
| `make verify` green | **Done.** |

## 8. Tasks satisfied differently from the wording

- **T014 (image vulnerability scan in CI)** — a Trivy job on the built images,
  failing on fixable HIGH/CRITICAL only. An unfixable CVE in a base image is not
  something this repository can act on, and a gate that cannot be made green is
  a gate somebody disables.
- **T022 / T050 (measure SC-001 on three platforms)** — the repository already
  had `tools/measure_first_investigation.py` and a three-platform CI job from
  feature 019. This feature adds the profile-aware plan and its budget assertion
  rather than a second measuring script.
- **T032 (leader-claimed scheduler across replicas)** — feature 016 already
  ships `platform/scheduler/claiming.py`. This feature contributes the
  deployment half: the enterprise topology declares `leader_claimed`, and the
  chart runs the scheduler on every replica rather than offering a
  "scheduler on replica zero" setting, which would be a single point of failure
  wearing a configuration option's clothes.
- **T033 (chart lint and install against Kind)** — `helm lint`, three
  `helm template` renders covering the combinations that change the object
  graph, and `helm install --dry-run=server` against a Kind cluster. Not a real
  install: the workloads need images that job has not built and a database it
  has no reason to provision, and what is worth checking is that the API server
  accepts every manifest the chart produces.
- **T021 (golden template application during setup)** — `NINJASRE_SETUP_TEMPLATE`
  is declared and documented, and feature 013's `TemplateLibrary.golden()` is
  what applies it. The setup-time application itself is a first-run flow this
  feature does not otherwise touch.
- **T045 (local-model configuration path)** — `OLLAMA_BASE_URL` and
  `VLLM_BASE_URL` were already the mechanism; what this feature adds is
  `provider_is_local`, which treats *any* provider pointed at an on-host
  endpoint as local, so a vLLM behind the OpenAI wire satisfies the air-gapped
  check without a special case.

## 9. `docs/provenance-map.md` (T052) not touched, and no `make check-provenance`

Per `CLAUDE.md` that file is gitignored and never linked from a committed file,
so editing the local copy would have no effect on what ships. `make
check-provenance` does not exist in this repository — the Makefile has no such
target — so there was nothing to confirm.

## 10. One `ruff.toml` per-file ignore added

`gateway/http/asgi.py` gets `ARG002`, with the same justification as the eleven
entries already there: the stand-in for an unconfigured investigation runtime
refuses every call without reading its arguments, and it keeps the port's full
signature so the real runner is a drop-in and the routes keep one collaborator
rather than a branch. This is following the file's existing convention, not
loosening the gate — the alternative was `*args, **kwargs`, which would have
made the stand-in *stop* being substitutable.

## 11. Test-first sequencing, adapted for scale

Phase 1 was genuinely test-first: the misconfiguration fixture set and its
assertions (T001/T002) were written and confirmed red on `ModuleNotFoundError`
before `platform/startup/validation.py` existed, and the concurrent-replica test
(T008) was red for a real reason — four replicas each claiming the migration —
before the port changed to fix it (§3).

For the later phases the test landed with the module rather than before the
package existed, for the same reason feature 020's deviations record: a test
written against a package that does not exist yet fails on `ImportError`, which
proves nothing about the behaviour it describes. Every SC in the definition of
done has a test that drives real collaborators — the real `FakePersistence`, the
real ports, the real ReAct loop, a real socket — rather than a mock standing in
for the boundary being proven.
