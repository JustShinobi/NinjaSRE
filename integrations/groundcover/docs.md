# groundcover

groundcover's eBPF-derived service metrics and the monitors currently firing, for clusters instrumented without code changes.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | groundcover API key for the backend this cluster reports to | yes | yes |

```bash
ninjasre integrations setup groundcover
ninjasre integrations verify groundcover
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `saas`.

groundcover is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `api.groundcover.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

the groundcover portal → Settings → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `metrics:read` | evaluate PromQL against the ingested series | `groundcover_metric_statistics` |
| `monitors:read` | list monitors and their current state | `groundcover_active_alerts` |

groundcover has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **groundcover can be self-hosted (inCloud) or SaaS**, and the API host differs. The declared default is the SaaS one; a self-hosted backend declares its own.
- **eBPF sees the wire, not the application.** A metric here describes requests and latency and knows nothing about a business error that returned 200.
- **Metrics are per cluster.** A workload name is unique inside a cluster and not across them, which matters when two clusters run the same service.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
