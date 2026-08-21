# Linear

What Linear already tracks about a symptom: how many issues match, in what state, and which are worth reading before another is filed.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Linear API key | yes | yes |

```bash
ninjasre integrations setup linear
ninjasre integrations verify linear
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Linear → Settings → API → Personal API keys

| Permission | What it grants | Without it |
|---|---|---|
| `read` | read issues and their state | `linear_issue_statistics`, `linear_recent_issues` |
| `viewer` | read the key's own identity, which the probe uses | `linear_issue_statistics` |

Linear has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **GraphQL answers 200 for a rejected query**, with the problem in an `errors` array. An empty result and a bad query look the same until that is read.
- **A personal API key carries the person's access.** An offboarded engineer's key stops working with nothing in NinjaSRE changing.
- **Linear's complexity budget is per request**, so a query that selects deeply nested fields is refused rather than answered slowly.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
