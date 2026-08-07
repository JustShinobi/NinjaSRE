# Temporal

Temporal workflow executions over its HTTP API: which are open, which failed, and how that distribution has changed.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Temporal Cloud API key, or the token your self-hosted frontend accepts | yes | yes |
| `namespace` | Temporal namespace | no | yes |

```bash
ninjasre integrations setup temporal
ninjasre integrations verify temporal
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Temporal is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `temporal.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Temporal Cloud → Settings → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `workflows:read` | list workflow executions | `temporal_pipeline_health`, `temporal_recent_failures` |
| `namespaces:read` | read the namespace, which the probe uses | `temporal_pipeline_health` |

Temporal has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Temporal's primary interface is gRPC.** The HTTP API is a gateway over it and is available on Temporal Cloud and on a self-hosted frontend that enables it; a deployment without it is not reachable through an HTTP credential proxy.
- **Visibility queries are eventually consistent** and lag the actual state by seconds, which matters when the question is whether something is running now.
- **The namespace is part of the path** and is substituted by the proxy from the stored configuration.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
