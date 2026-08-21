# VictoriaLogs

LogsQL against VictoriaLogs, counted by stream field before any line is read, for the estates that chose it for its ingest cost.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts VictoriaLogs | yes | yes |
| `tenant` | AccountID:ProjectID for a multi-tenant install | no | no |

```bash
ninjasre integrations setup victorialogs
ninjasre integrations verify victorialogs
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

VictoriaLogs is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `victorialogs.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your reverse proxy or vmauth configuration — VictoriaLogs ships no authentication

| Permission | What it grants | Without it |
|---|---|---|
| `select` | run LogsQL queries against the tenant's streams | `victorialogs_log_statistics`, `victorialogs_sample_logs` |
| `hits` | read the hit counts the connectivity probe uses | `victorialogs_log_statistics` |

VictoriaLogs has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **VictoriaLogs answers newline-delimited JSON**, one object per line, rather than one document. The client reads it as a list; a vendor change to that framing is what the scenario catches.
- **There is no pagination.** `limit` is the only bound and the walk stops after one response.
- **Multi-tenancy is a header, not a path.** A tenant left unset reads the default account, which on a shared install is somebody else's data.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
