# Hermes

Hermes log tailing and classification: what a stream is currently emitting, grouped by the class its own model assigned.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `endpoint` | Where your Hermes answers, scheme and port included | no | yes |
| `api_key` | Hermes access token for the workspace holding this stream | yes | yes |
| `stream` | Default stream to read | no | no |

The endpoint goes to the configuration tree rather than the vault — it is not
part of the credential, and it is where the credential proxy reads its egress
allow-list from, so declaring the address and permitting it stay one act.

```bash
ninjasre integrations setup hermes
ninjasre integrations verify hermes
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Hermes is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `hermes.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

the Hermes console → Access tokens

| Permission | What it grants | Without it |
|---|---|---|
| `logs:read` | search and tail the workspace's streams | `hermes_log_statistics`, `hermes_sample_logs` |
| `streams:list` | list streams, which the connectivity probe uses | `hermes_log_statistics` |

Hermes has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Classification is a model's opinion**, not a field the emitter set. It is useful for grouping and is not evidence on its own; the message is.
- **Tailing is bounded by the workspace's retention**, which is short by design.
- **A stream that has been idle produces no entries**, which is indistinguishable from a query that matched nothing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
