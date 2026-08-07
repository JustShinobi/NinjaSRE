# Honeycomb

Honeycomb's query engine over trace events: where latency and errors concentrate in a dataset, and the slowest traces behind that concentration.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | Honeycomb API key with query access to the datasets you investigate | yes | yes |
| `dataset` | The dataset this integration queries | no | yes |

```bash
ninjasre integrations setup honeycomb
ninjasre integrations verify honeycomb
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `eu`.

## Permissions

Environment settings → API keys, on the environment holding the dataset

| Permission | What it grants | Without it |
|---|---|---|
| `query` | run queries against a dataset's events | `honeycomb_trace_statistics`, `honeycomb_slow_traces` |
| `auth:read` | read what the key is allowed to do, which the probe uses | `honeycomb_trace_statistics` |

Honeycomb has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The dataset is part of the path.** A key scoped to one environment cannot read another's dataset even though the host is the same.
- **Honeycomb samples at ingest.** A count here is a count of sampled events, and the sample rate is per dataset — multiply before comparing against a metric.
- **`/1/auth` reports what the key can do**, which is unusual and worth using: this is one of the few vendors where a permission can be read rather than inferred.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
