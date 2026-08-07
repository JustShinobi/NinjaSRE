# Railway

Railway deployments and their status, for the services this project runs on it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Railway API token, project-scoped or account-scoped | yes | yes |
| `project_id` | Railway project id the queries are scoped to | no | no |

```bash
ninjasre integrations setup railway
ninjasre integrations verify railway
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Railway → Account Settings → Tokens, or a project token from project settings

| Permission | What it grants | Without it |
|---|---|---|
| `deployments:read` | read the project's deployments | `railway_pipeline_statistics`, `railway_failed_runs` |
| `me:read` | read the token's own identity, which the probe uses | `railway_pipeline_statistics` |

Railway has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **GraphQL returns 200 for a rejected query**, with the problem in an `errors` array. An empty result and a bad query look the same until that is read.
- **A project token is scoped to one project** and ignores the project id in the query, which is safer and occasionally surprising.
- **Deployment logs are a separate subscription-style endpoint** and are not part of the listing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
