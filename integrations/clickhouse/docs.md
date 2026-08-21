# ClickHouse

ClickHouse over its HTTP interface: what the server is currently executing, and the slowest queries in the log.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | ClickHouse user with access to the system tables | yes | yes |
| `password` | That user's password | yes | yes |
| `database` | Default database for queries | no | no |

```bash
ninjasre integrations setup clickhouse
ninjasre integrations verify clickhouse
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

ClickHouse is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `clickhouse.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your ClickHouse users.xml or the cloud console's SQL console user

| Permission | What it grants | Without it |
|---|---|---|
| `SELECT on system.processes` | read what is executing now | `clickhouse_session_statistics` |
| `SELECT on system.query_log` | read the completed-query log | `clickhouse_slow_queries` |

ClickHouse has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **ClickHouse is the one database here with a first-class HTTP interface.** Its native protocol is faster; the HTTP one is what allows a proxied credential, which is the trade this integration makes deliberately.
- **`system.query_log` has to be enabled**, and on a busy cluster it is often sampled or has a short TTL. An empty answer can mean the log is off.
- **Queries here are read-only by convention, not by enforcement.** The user this integration authenticates as should have `readonly=1` set on it.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
