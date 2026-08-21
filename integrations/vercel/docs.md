# Vercel

Vercel deployments: how the recent ones have gone for a project, and the ones that errored, which is usually the whole story for a frontend incident.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Vercel access token with read access to the team's projects | yes | yes |
| `team` | Vercel team id, for a token that spans several | no | no |

```bash
ninjasre integrations setup vercel
ninjasre integrations verify vercel
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Vercel → Account Settings → Tokens

| Permission | What it grants | Without it |
|---|---|---|
| `deployments:read` | list deployments and their state | `vercel_pipeline_statistics`, `vercel_failed_runs` |
| `user:read` | read the token's own account, which the probe uses | `vercel_pipeline_statistics` |

Vercel has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Pagination is by timestamp, not a cursor.** `pagination.next` is the millisecond timestamp to pass as `until`, and a walk that treats it as opaque still works because it is passed straight back.
- **A token without a team id sees only personal projects**, which on a team account is an empty list rather than an error.
- **Build logs are a separate endpoint per deployment**, so 'why did it fail' is a second call rather than part of the listing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
