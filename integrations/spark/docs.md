# Spark

Spark's history and status API: which applications and jobs are in which state, and the ones that failed.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts the Spark UI | yes | yes |

```bash
ninjasre integrations setup spark
ninjasre integrations verify spark
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Spark is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `spark-history.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your reverse proxy or Knox gateway — the Spark UI has no authentication of its own

| Permission | What it grants | Without it |
|---|---|---|
| `applications:read` | list applications and their attempts | `spark_pipeline_health`, `spark_recent_failures` |
| `version:read` | read the version, which the probe uses | `spark_pipeline_health` |

Spark has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The history server only knows about applications that finished writing an event log.** A driver that was killed leaves nothing behind, which is exactly the case an investigation cares about most.
- **Job-level and stage-level detail is one call per application**, so 'which stage failed' is a second request rather than part of the listing.
- **Spark ships no authentication.** Whatever fronts the UI is what the token authenticates against.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
