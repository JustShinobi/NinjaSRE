# Backup and restore

One PostgreSQL instance holds everything NinjaSRE persists (ADR 0004), so the
backup procedure is `pg_dump` and the restore procedure is `psql`. That is the
whole point of the single-datastore decision: there is no second service whose
snapshot has to be consistent with this one.

Two things about this schema are not obvious, and both are the kind of thing
discovered during a restore rather than before one. They are the reason this
page exists, and each is exercised by
`tests/contract/persistence/test_operations.py` rather than merely written down.

---

## Take a backup

```bash
pg_dump "$NINJASRE_DATABASE_URL" --no-owner --no-privileges > ninjasre-$(date +%F).sql
```

Plain text rather than the custom format, so the restore needs `psql` and
nothing else. A backup that requires a second tool to read is one more thing to
get wrong at three in the morning.

`--no-owner` and `--no-privileges` let the dump restore under whichever role the
target database uses. Without them, a restore into a differently-owned database
fails on every `ALTER TABLE ... OWNER TO`.

### The backup does not contain your credentials

Credential values are encrypted at rest with the key in
`NINJASRE_DATABASE_ENCRYPTION_KEY`, so the dump carries ciphertext. A restored
database is only usable by a deployment configured with **the same key**.

**Back the key up separately, and not beside the dump.** A dump and its key in
one place is a dump with the credentials in it.

`platform.persistence.postgres.crypto.generate_key` produces one; the health
check reports at startup when the configured key cannot open what is stored, so
a key that did not survive a move surfaces then rather than during the first
incident that needs it.

---

## Restore

```bash
createdb --template=template0 ninjasre_restored
psql "$RESTORED_URL" --set ON_ERROR_STOP=1 < ninjasre-2026-08-05.sql
```

### `--template=template0` is required, not a preference

Apache AGE keeps its catalogue in a schema called `ag_catalog`, and `pg_dump`
captures the `CREATE SCHEMA` for it. PostgreSQL's default template is
`template1`, and any deployment that installed the extensions into `template1`
— which is the ordinary way to make them available to new databases — produces
a target where that schema already exists. The restore then fails on its first
statement:

```
ERROR:  schema "ag_catalog" already exists
```

`template0` is the pristine template. Restoring into it lets the dump recreate
the extensions exactly as the source had them, which is also what makes the
restored database a faithful copy rather than one wearing the target's
extensions.

### After the restore

Point a deployment at the restored database with the original encryption key
and check its health endpoint. It reports four things, and all four have to be
right before the restore counts:

| Reported | Means |
|---|---|
| connectivity | the database answers |
| `vector` available | episodic recall and knowledge retrieval work |
| `age` available | topology answers work; degraded rather than fatal without it |
| migrations at head | the schema matches the code that will use it |
| no undecryptable credentials | the key that opened the source opens this one |

---

## What retention will and will not remove

Retention windows are per data class and configurable
(`config/constants/persistence.py`). Audit events are **exempt** and no
retention pass may delete them — `AuditRepository` has no delete method, and
`RetentionPolicy` refuses to be constructed with a finite window for them.

A backup therefore always contains the complete audit trail, however aggressively
traces and sessions are aged out.

---

## Rolling a release back

Migrations are reversible and every one has a tested `downgrade`:

```bash
uv run alembic -c platform/persistence/migrations/alembic.ini downgrade <revision>
```

A downgrade drops what its upgrade created, so **it removes data**. It is a way
to get a schema back to a known point, not a way to undo a bad deploy without
losing the writes that happened during it. Take a backup first.

Migrations are applied automatically at startup under a PostgreSQL advisory
lock, so replicas starting together do not race: one applies, the others wait
and then find the schema already at head.
