# Sourcegraph

Code search across every repository at once: where a symbol, a string, or a configuration key actually appears.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Sourcegraph access token | yes | yes |

```bash
ninjasre integrations setup sourcegraph
ninjasre integrations verify sourcegraph
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Sourcegraph is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `sourcegraph.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Sourcegraph → Settings → Access tokens

| Permission | What it grants | Without it |
|---|---|---|
| `search` | run code searches across the indexed repositories | `sourcegraph_change_statistics`, `sourcegraph_recent_changes` |
| `user:read` | read the token's own identity, which the probe uses | `sourcegraph_change_statistics` |

Sourcegraph has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Search results are scoped by the token's repository permissions**, so two engineers running the same search legitimately get different answers.
- **The streaming endpoint is server-sent events**; this client reads the buffered form, which is bounded by `display` and does not stream.
- **Indexing lags a push** by minutes on a large instance, so a change made during an incident may not be searchable yet.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
