# Flink

Flink's JobManager REST API: which jobs are running, and the ones that failed or restarted, which is where a streaming backlog starts.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts the JobManager | yes | yes |

```bash
ninjasre integrations setup flink
ninjasre integrations verify flink
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Flink is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `flink.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your reverse proxy or ingress — the JobManager REST API has no authentication of its own

| Permission | What it grants | Without it |
|---|---|---|
| `jobs:read` | read the job overview and per-job detail | `flink_pipeline_health`, `flink_recent_failures` |
| `config:read` | read the cluster config, which the probe uses | `flink_pipeline_health` |

Flink has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The JobManager has no authentication.** Whatever fronts it is what the token authenticates against, and an unfronted JobManager accepts anything.
- **There is no pagination.** Every job comes back in one response, which is fine for a cluster and would not be for a fleet.
- **Checkpoint and watermark detail is per job**, so 'how far behind is it' is a second call rather than part of the overview.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
