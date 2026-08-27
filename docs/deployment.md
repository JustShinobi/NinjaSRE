# Deploying NinjaSRE

Three ways to run it, one setting to choose between them, and the operational
story each one needs. This page is for the person who has to answer: which
profile, how do I start, how do I upgrade, how do I get my data back, what
happens if I lose the encryption key, and can I run this with no internet at
all.

**The short version.** Copy `deploy/compose/.env.example` to `.env`, put in one
provider API key and an encryption key, and run `docker compose up -d`. Four
containers start, migrations apply, and the admin token is printed once.

## Choosing a profile

`NINJASRE_DEPLOYMENT_PROFILE` picks one of four shapes. It decides the sandbox,
where the credential proxy runs, and how much work the deployment takes at
once — all three together, because a deployment that ran the in-process proxy
with cluster concurrency would be a combination nobody chose and nobody tested.

| | `dev` | `homelab` | `standard` | `enterprise` |
|---|---|---|---|---|
| Components | app, Postgres | app, console, Postgres, proxy | app, console, Postgres, proxy | app replicas, console, sandbox pods, proxy, Postgres |
| Containers | 2 | **4**, capped | **4** | Helm-managed |
| Resource ceiling | none | 4 GiB, 2 CPUs, enforced | none | Helm limits |
| Credential proxy | in-process | container | container | deployment |
| Sandbox isolation | `process` | `container` | `container` | `kubernetes` + Envoy |
| Identity | local admin token | local admin token | local admin token or SSO | SSO |
| Scheduler | in-process | in-process | in-process | leader-claimed across replicas |
| For | contributing | one person's own infrastructure | a team self-hosting | regulated or multi-tenant |

You do not configure the sandbox separately. If you set
`NINJASRE_SANDBOX_PROFILE` to something the deployment profile does not imply,
startup refuses and says which two settings disagree — a deployment that
silently took one of them would be running with an isolation guarantee its
operator does not believe it has.

`homelab` is the same four components as `standard` with one difference that
matters: every container carries a memory and CPU limit, the four sum to 4 GiB
and 2 CPUs, and a test holds the compose file and the declared numbers to each
other. A footprint nothing enforces is one an operator discovers when their
media server starts stuttering. It also assumes the deployment is running beside
— often *on* — the infrastructure it watches, which is why it is the profile
that warns when no external heartbeat destination is configured.

```sh
cd deploy/compose
docker compose -f docker-compose.homelab.yml up -d
```

The `standard` profile is four containers and a test asserts it still is. Every
additional stateful service is a backup strategy, an upgrade path, and a failure
mode you inherit without asking for one.

## First run

```bash
cd deploy/compose
cp .env.example .env
```

Two values are required and everything else has a working default:

- **one provider credential** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or
  whichever provider you use;
- **`NINJASRE_DATABASE_URL`** — already set to the Compose deployment's own
  PostgreSQL.

You will also want an encryption key before you configure any integration:

```bash
openssl rand -base64 32
```

Then:

```bash
docker compose up -d
docker compose logs app | grep -A3 "admin token"
```

The admin token is printed once at first start. Set `NINJASRE_ADMIN_TOKEN`
yourself if you would rather choose it.

`.env.example` documents every setting with its default, whether it is required,
and what it affects. It is generated from the settings catalogue in the code, so
it cannot go stale — `make check-env-example` fails the build if it has.

To check a configuration before starting anything:

```bash
make deploy-preflight
```

It reports every problem at once, each naming the setting and what to do about
it, and then prints every destination your configuration permits the deployment
to reach.

## Startup, in order

```
resolve the profile → validate configuration → verify the encryption key
    → migrate under an advisory lock → check schema compatibility
    → report readiness per dependency
```

Two positions in that list are load-bearing.

**The key is verified before migrations.** A deployment booting with the wrong
key works perfectly until the first credential is needed, and the first
credential is needed during an incident. Checking first means a key that did not
survive a restore fails in seconds — before a schema change, so the fix is "put
the right key back" rather than "put the right key back and work out what the
half-migrated database now is".

**Validation comes before both.** Every check after it needs a database URL, and
a connection failure caused by an unset variable reports as a connection
failure.

Readiness names the dependency that is not ready, per dependency, rather than
answering yes or no. `GET /health/ready` tells you whether the database is
unreachable, the schema is behind, the graph extension is missing, or stored
credentials will not decrypt — four different problems with four different
responses, and only some of them take the deployment out of rotation.

## Upgrading

Migrations apply automatically at startup, under a PostgreSQL advisory lock, so
concurrent replicas do not race. The loser of the race waits, finds the schema
already at head, and applies nothing.

**Back up first.** Always, and especially across a version skip.

```bash
make backup INTO=/var/backups/ninjasre
docker compose pull && docker compose up -d
```

An upgrade that skips several versions applies every revision in between, in
order. A release that finds a schema it does not recognise — an older
application in front of a newer database, which is what a rollback deploy
produces — refuses to start rather than writing rows the new constraints do not
describe.

If a migration fails part-way, every revision before the failure has committed
and the startup error says which one the schema is at. Fix the cause and start
again: the run resumes from where it stopped. If you would rather go back,
restore the backup you took before the upgrade.

On Kubernetes, the chart runs migrations as a `pre-upgrade` job that must
complete before the rollout begins, so a migration that cannot apply is a failed
job with the reason in one place rather than several replicas crash-looping.

### Rolling back

1. Scale the application to zero, or `helm rollback` with the migration hook
   disabled.
2. Restore the backup taken before the upgrade
   (`make restore ARCHIVE=...`).
3. Start the previous release.

A rollback without a restore is only safe when the upgrade applied no
migrations. NinjaSRE refuses to run an older release against a newer schema
rather than letting you find out which case you were in.

## Backup and restore

One PostgreSQL instance holds everything — relational rows, `pgvector`
embeddings, and the Apache AGE graph — so one command captures all of it.

```bash
make backup                    # writes ./backups/ninjasre-<timestamp>.tar.gz
make restore ARCHIVE=./backups/ninjasre-20260807T090000Z.tar.gz
```

The archive holds the dump and a **manifest**, and the manifest is read first.
It records the schema revision, the PostgreSQL version, the extension versions,
a row count per table, and a fingerprint of the encryption key — never the key.
Reading it before writing anything is what turns three silent failures into
three refusals with reasons:

- a backup from a **newer release**, whose schema this code cannot describe;
- a backup needing an **extension this server does not have**, which would
  restore without the data that needed it;
- a backup whose credentials were encrypted under a **different key**, which
  would restore perfectly and leave every integration unable to authenticate.

An older backup is not refused: it is restored, and the running release migrates
it forward at startup.

The row counts are what makes "integrity verified" a claim with a number behind
it. An archive truncated while it was being copied is refused rather than
restored quietly.

**The dump contains your credentials as ciphertext.** Back the encryption key up
separately, and not beside the dump — a dump and its key in one place is a dump
with the credentials in it.

`docs/backup-and-restore.md` covers the two schema details that are discovered
during a restore rather than before one.

## Keys

The encryption key is supplied by you and NinjaSRE never generates one. A key
generated at first start has to live somewhere the process can read it again —
a container layer, a bind mount, a compose file — and you would not know it
exists until you restored a backup on another host and found every credential
unreadable.

### Rotating

Rotation is online. The process doing it holds both keys: the new one writes,
the old one is a read-only fallback, so a credential the rotation has not
reached yet is still readable and a request arriving mid-run notices nothing.

```bash
NINJASRE_DATABASE_ENCRYPTION_KEY=<new key> \
  make rotate-key ORG=acme PREVIOUS_KEY=<old key>
```

It reports how many credentials were rewritten and says explicitly when the
previous key is no longer needed. **Keep the old key until a run reports every
credential rewritten** — "probably finished" is not a state to drop a key on.
Then restart the deployment with the new key alone.

### If the key is lost

This is unpleasant and it is not terminal.

**Lost:** every stored integration credential. They are AES-256-GCM ciphertext
under the key that has gone, and no procedure recovers them.

**Unaffected:** every investigation, trace, and piece of evidence; the episode
corpus and the strategies synthesised from it; the service topology and
knowledge base; configuration, identity, roles, and the audit trail.

**Recovery:**

1. Generate a new key and configure it.
2. Delete the unreadable credential rows — startup names them for you.
3. Re-enter each integration's credential.
4. Rotate those credentials at the vendor. A key is usually lost alongside
   whatever else was on that host.

## Air-gapped installation

A deployment with no internet access at all is a supported shape, and it is why
provider neutrality is constitutional: with a local model, a no-egress
deployment is fully functional.

On a machine that does have a network:

```bash
sh deploy/images/bundle.sh ninjasre-images.tar.gz
```

That exports the four images as one archive — one file rather than four, because
the thing carrying it is usually a USB stick and a person. The local model is
not in it and cannot be: it is gigabytes and Ollama and vLLM each have their own
distribution story. Pull it separately.

On the air-gapped host:

```bash
docker load --input ninjasre-images.tar.gz
```

Then configure a local model and turn the check on:

```
OLLAMA_BASE_URL=http://ollama:11434/v1
NINJASRE_AIR_GAPPED=true
```

`NINJASRE_AIR_GAPPED` refuses to start if any setting implies an outbound
connection, naming the setting. It is not a firewall — the firewall is yours —
but it catches the deployment that *believes* it is air-gapped and is not, which
is the one that matters.

## Behind a proxy that terminates TLS

Point `NINJASRE_CA_BUNDLE` at a PEM bundle to trust in addition to the system
store:

```
NINJASRE_CA_BUNDLE=/etc/ssl/certs/corporate-ca.pem
```

Startup checks the file is readable and refuses if it is not — an unreadable
bundle fails every outbound call with a verification error, and the reason would
otherwise be nowhere.

There is deliberately no setting that turns certificate verification off. A
deployment that skipped it would send credentials to whoever answered.

## Kubernetes

```bash
kubectl create namespace ninjasre
kubectl -n ninjasre create secret generic ninjasre-encryption-key \
  --from-literal=key="$(openssl rand -base64 32)"
kubectl -n ninjasre create secret generic ninjasre-database \
  --from-literal=url='postgresql://...'
kubectl -n ninjasre create secret generic ninjasre-provider \
  --from-literal=api-key='...'

helm install ninjasre deploy/helm/ninjasre --namespace ninjasre
```

Every credential in the chart is a reference to a Secret you created — a name
and a key, never a value. A values file that accepted an API key would be a
values file that ends up in a Git repository with the key in it.

An **external** PostgreSQL is the default and the recommendation. In a regulated
environment somebody already runs one with the backup schedule, the retention
policy, and the failover story that estate requires; a StatefulSet in this
release is a second database with none of them. The in-cluster option exists for
an evaluation and needs an image carrying both extensions — the chart refuses to
guess one, because a stock `postgres` image starts and then fails on the first
vector write.

Sandbox pods get an Envoy sidecar carrying the egress allow-list and a
NetworkPolicy denying every other route out. Neither is sufficient alone: a
sidecar without the policy is advice, and a policy without the sidecar cannot
express "this vendor's hostname and nothing else".

## What can this reach?

Every destination NinjaSRE may connect to is derived from a setting, and the
setting's name travels with it:

```bash
make deploy-preflight
```

The list cannot grow by something reaching a host nobody declared — that is the
property Article X is about, and it is checked rather than claimed. A full
investigation runs under a socket monitor in the test suite, and it opens no
socket at all.
