# Tempo

TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Tempo bearer token, or the Grafana Cloud access policy token | yes | yes |
| `tenant` | Tenant id sent as X-Scope-OrgID on a multi-tenant install | no | no |

```bash
ninjasre integrations setup tempo
ninjasre integrations verify tempo
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Tempo is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `tempo.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Grafana Cloud → Access Policies, or whatever your gateway issues for a self-hosted install

| Permission | What it grants | Without it |
|---|---|---|
| `traces:read` | search the trace store | `tempo_trace_statistics`, `tempo_slow_traces` |
| `echo` | the unauthenticated liveness endpoint the probe uses | `tempo_trace_statistics` |

Tempo has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **TraceQL search needs the search feature enabled** on the Tempo deployment; without it, search returns an error and only trace-by-id lookups work.
- **Tempo has no cursor.** `limit` bounds the answer and there is no second page.
- **Times are Unix seconds** on the search endpoint, unlike most of the tracing vendors here, which use microseconds.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
