# Prefect

Prefect flow runs: which are in which state, and the ones that failed, for the estates orchestrating their pipelines with it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Prefect Cloud API key, or the token your self-hosted server accepts | yes | yes |
| `workspace` | Prefect Cloud workspace path, account/workspace | no | no |

```bash
ninjasre integrations setup prefect
ninjasre integrations verify prefect
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `cloud`.

Prefect is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `api.prefect.cloud`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Prefect Cloud → Account → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `flow_runs:read` | read flow runs and their state | `prefect_pipeline_health`, `prefect_recent_failures` |
| `health:read` | read server health, which the probe uses | `prefect_pipeline_health` |

Prefect has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Prefect Cloud puts the workspace in the path**, and a self-hosted server does not. The declared host is the cloud one; a self-hosted deployment declares its own and the paths differ.
- **Filters are POST bodies, not query parameters**, which is unusual and is why this client posts to read.
- **`CRASHED` and `FAILED` are different states.** A crash is infrastructure and a failure is the flow's own, and treating them alike hides which one happened.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
