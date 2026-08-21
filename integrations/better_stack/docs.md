# Better Stack

Better Stack's log search and the monitors it is currently reporting as down, for teams using it as both log store and uptime checker.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Better Stack API token, from the team whose sources you query | yes | yes |

```bash
ninjasre integrations setup better_stack
ninjasre integrations verify better_stack
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Better Stack → Settings → API tokens

| Permission | What it grants | Without it |
|---|---|---|
| `logs:read` | query the sources this token can see | `better_stack_log_statistics`, `better_stack_sample_logs` |
| `sources:read` | list the sources a query may name | `better_stack_log_statistics` |

Better Stack has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Retention is short on the lower plans** — days rather than weeks — and a query past it returns nothing rather than an error.
- **Live tail is optimised for recency.** A query far in the past is slower and may be refused, which is the opposite of what an incident review wants.
- **Source names, not indices.** A query naming a source the token cannot see returns empty rather than 403.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
