# VictoriaMetrics

MetricsQL against VictoriaMetrics and the alerts vmalert is holding, for the estates that use it as a long-term Prometheus store.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by vmauth or whatever fronts VictoriaMetrics | yes | yes |

```bash
ninjasre integrations setup victoriametrics
ninjasre integrations verify victoriametrics
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

VictoriaMetrics is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `victoriametrics.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your vmauth configuration — VictoriaMetrics ships no authentication of its own

| Permission | What it grants | Without it |
|---|---|---|
| `select` | evaluate MetricsQL over the stored series | `victoriametrics_metric_statistics` |
| `alerts:read` | read the alerts vmalert is holding | `victoriametrics_active_alerts` |

VictoriaMetrics has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **MetricsQL is a superset of PromQL**, so a query written here may not run against Prometheus even though the reverse is always true.
- **No pagination.** A query matching many series returns them all in one response, so a broad query has to be narrowed rather than paged.
- **The alerts endpoint is vmalert's, not the storage node's**, and a deployment without vmalert answers 404 rather than an empty list.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
