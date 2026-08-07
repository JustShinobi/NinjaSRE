# Dagster

Dagster run state through its GraphQL API: which runs are in which status, and the failures behind a stale asset.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Dagster Cloud user token, or the token your self-hosted webserver accepts | yes | yes |
| `deployment` | Dagster Cloud deployment name | no | no |

```bash
ninjasre integrations setup dagster
ninjasre integrations verify dagster
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Dagster is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `dagster.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Dagster Cloud → Organization Settings → Tokens

| Permission | What it grants | Without it |
|---|---|---|
| `runs:read` | read run status through the GraphQL API | `dagster_pipeline_health`, `dagster_recent_failures` |
| `version:read` | read the version, which the probe uses | `dagster_pipeline_health` |

Dagster has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **GraphQL answers 200 for a rejected query.** The problem is in an `errors` array, so an empty result and a bad query look the same until that is read.
- **Union types mean the answer may be an error object under the same key**, which is why the field selection uses an inline fragment.
- **Dagster Cloud puts the deployment in the path**; a self-hosted webserver does not, and the declared host is the self-hosted shape.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
