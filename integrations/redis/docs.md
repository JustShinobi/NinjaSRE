# Redis Cloud

The Redis Cloud control plane: which databases exist in a subscription and in what state, which is what an HTTP-reachable Redis can answer.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | Redis Cloud account key | yes | yes |
| `secret_key` | Redis Cloud user secret key | yes | yes |

```bash
ninjasre integrations setup redis
ninjasre integrations verify redis
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Redis Cloud → Access Management → API Keys

| Permission | What it grants | Without it |
|---|---|---|
| `subscriptions:read` | list subscriptions and their status | `redis_session_statistics`, `redis_slow_queries` |
| `databases:read` | read database state within a subscription | `redis_slow_queries` |

Redis Cloud has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **This is Redis Cloud's control plane, not a Redis server.** Keyspace, slow log, and `INFO` are RESP, which an HTTP credential proxy cannot carry — a self-hosted Redis is not reachable through this integration.
- **Every account key is paired with a user secret key**, and both headers are required. One alone is a 401 that does not say which is missing.
- **API access is off by default** on a Redis Cloud account and is enabled per account rather than per key.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
