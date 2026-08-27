# Deployment

Three shapes to run this in, one setting to choose between them, and the
operational story each one needs: how you start, how you upgrade, how you get
your data back, what happens if you lose the encryption key, and whether you can
run it with no internet at all.

The [quickstart](../quickstart/index.md) gets you a working deployment. This
page is for the person who has to keep it working.

## Choosing a profile

`NINJASRE_DEPLOYMENT_PROFILE` picks one of four shapes. It decides the sandbox,
where the credential proxy runs, and how much work the deployment takes at once —
all three together, because a deployment running the in-process proxy with
cluster concurrency would be a combination nobody chose and nobody tested.

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

You do not configure the sandbox separately. Set `NINJASRE_SANDBOX_PROFILE` to
something the deployment profile does not imply and startup refuses, naming the
two settings that disagree — a deployment that silently took one of them would
be running with an isolation guarantee its operator does not believe it has.

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

`standard` is four containers and a test asserts it still is. Every additional
stateful service is a backup strategy, an upgrade path, and a failure mode you
inherit without having asked for one.

## Checking a configuration before starting anything

```sh
make deploy-preflight
```

It reports every problem at once, each naming the setting and what to do, and
then prints every destination your configuration permits the deployment to
reach. That last list is the one worth reading twice.

## Upgrading

Migrations apply at startup under a PostgreSQL advisory lock, so concurrent
replicas do not race — the loser waits, finds the schema at head, and applies
nothing.

**Back up first.** Always, and especially across a version skip.

```sh
make backup INTO=/var/backups/ninjasre
docker compose pull
docker compose up -d
```

An upgrade that skips several versions applies every revision in between, in
order. A release that finds a schema it does not recognise — an older
application in front of a newer database, which is what a rollback deploy
produces — refuses to start rather than writing rows the new constraints do not
describe.

To go back: scale to zero, restore the backup you took before the upgrade, start
the previous release. A rollback without a restore is only safe when the upgrade
applied no migrations, and NinjaSRE refuses to run an older release against a
newer schema rather than letting you discover which case you were in.

## Backup and restore

One PostgreSQL instance holds everything — relational rows, `pgvector`
embeddings, and the Apache AGE graph — so one command captures all of it.

```sh
make backup
make restore ARCHIVE=./backups/ninjasre-20260807T090000Z.tar.gz
```

The archive holds the dump and a manifest, and the manifest is read *first*. It
records the schema revision, the PostgreSQL version, the extension versions, a
row count per table, and a fingerprint of the encryption key — never the key.
Reading it before writing anything turns three silent failures into three
refusals with reasons: a backup from a newer release, a backup needing an
extension this server does not have, and a backup whose credentials were
encrypted under a different key.

An older backup is not refused. It is restored, and the running release migrates
it forward at startup.

**The dump contains your credentials as ciphertext.** Back the encryption key up
separately, and not beside the dump. A dump and its key in one place is a dump
with the credentials in it.

## Keys

You supply the encryption key and NinjaSRE never generates one. A key generated
at first start has to live somewhere the process can read it again, and you
would not find out it existed until you restored a backup on another host and
found every credential unreadable.

Rotation is online:

```sh
make rotate-key ORG=acme PREVIOUS_KEY=<the old key>
```

The process holds both keys — the new one writes, the old one is a read-only
fallback — so a credential rotation has not reached yet is still readable and a
request arriving mid-run notices nothing.

## Running with no internet

```ini
NINJASRE_AIR_GAPPED=true
```

The deployment refuses to start if any setting implies an outbound connection.
It is not a firewall — the firewall is yours — but it catches the deployment
that *believes* it is air-gapped and is not, which is the failure mode that
matters, because nobody checks a belief.

With a local model configured via an endpoint like `OLLAMA_BASE_URL`, that is a deployment
where nothing leaves the host at all.

Pull the images somewhere with a network and carry them in:

```sh
make bundle-images OUTPUT=ninjasre-images.tar.gz
```

If your egress goes through a proxy that terminates TLS, point
`NINJASRE_CA_BUNDLE` at a PEM bundle to trust in addition to the system store.
Hosts you have consciously permitted go in `NINJASRE_EGRESS_ALLOWLIST`;
everything your configuration already names is permitted by being configured.

## Observability

Nothing is exported until you say where to:

```ini
NINJASRE_OTEL_ENDPOINT=http://otel-collector:4318
```

That is an OTLP/HTTP base URL, and one setting covers traces, metrics, and logs.
Unset — which is the default — nothing leaves the host and no socket is opened.

Reference dashboards for Grafana and Prometheus ship in `deploy/dashboards/`,
covering every metric family the deployment can emit. A collector that becomes
unavailable mid-run does not affect investigations: exports are dropped and
counted, and the count is in the diagnostic bundle.

## Things worth knowing before you need them

- `ninjasre doctor` reports what is broken *and the remedy for each thing*.
- `ninjasre doctor --bundle <path>` writes a redacted report — configuration
  without secrets, recent logs, health, versions. Nothing is transmitted; you
  read it and decide.
- `ninjasre integrations health` is one line, suitable for a cron entry.
- `ninjasre cost --since 2026-08-01` is what a period cost, per team and per run.
- `GET /health/ready` names the dependency that is not ready rather than
  answering yes or no. Four different problems get four different responses, and
  only some of them should take a replica out of rotation.
