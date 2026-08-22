# Loki

Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `endpoint` | Where your Loki answers, scheme and port included | no | yes |
| `token` | Loki bearer token, or the Grafana Cloud access policy token | yes | no |
| `tenant` | Tenant id sent as X-Scope-OrgID on a multi-tenant install | no | no |

```bash
ninjasre integrations setup loki
ninjasre integrations verify loki
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

`endpoint` is the exception: it is not a credential. It goes to the
configuration tree, not the vault, which is where the credential proxy already
reads its egress allow-list from — declaring the address and permitting it are
one act.

The token is optional because Loki ships no authentication of its own: a
self-hosted install that is not behind an auth proxy needs nothing here.

Declared regions: `self-hosted`.

Loki is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `loki.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Grafana Cloud → Access Policies, or whatever your gateway issues for a self-hosted install

| Permission | What it grants | Without it |
|---|---|---|
| `logs:read` | run LogQL queries against the tenant's streams | `loki_log_statistics`, `loki_sample_logs` |
| `labels:read` | list label names and values, which the probe uses | `loki_log_statistics` |

Loki has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Loki has no cursor.** A range query returns everything inside the window up to `limit` and stops; there is no second page to ask for. Narrow the window rather than expecting to page through it.
- **A query with no label matcher is rejected**, not answered slowly. That is a feature: an unlabelled query would scan every stream in the tenant.
- **Retention is per tenant and often short.** A query reaching past it returns no results rather than an error, which reads exactly like nothing having happened.
- **Statistics are computed here rather than by Loki**, over the capped page the query returned, and the result says so. A distribution over a capped sample is a different claim from one over everything.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
