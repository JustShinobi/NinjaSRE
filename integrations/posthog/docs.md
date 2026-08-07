# PostHog

PostHog's product analytics: how event volume moved during a window, and which feature flags are currently on.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | PostHog personal API key | yes | yes |
| `project_id` | PostHog project id | no | yes |

```bash
ninjasre integrations setup posthog
ninjasre integrations verify posthog
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `eu`, `self-hosted`.

## Permissions

PostHog → Settings → Personal API keys

| Permission | What it grants | Without it |
|---|---|---|
| `event:read` | read the project's events | `posthog_metric_statistics` |
| `feature_flag:read` | read feature flags and their state | `posthog_active_alerts` |

PostHog has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The project id is part of the path** and is substituted by the proxy, so a capability cannot read another project.
- **A personal API key carries the person's access**, so an offboarded engineer's key stops working with nothing in NinjaSRE changing.
- **Event ingestion is asynchronous**, so a window investigated immediately is incomplete and the shortfall looks like a drop.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
