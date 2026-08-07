# Jaeger

Jaeger's trace store: where a service's operations concentrate latency, and the slowest traces behind that concentration.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts the Jaeger query service | yes | yes |

```bash
ninjasre integrations setup jaeger
ninjasre integrations verify jaeger
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Jaeger is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `jaeger.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your reverse proxy or ingress — the Jaeger query service ships no authentication

| Permission | What it grants | Without it |
|---|---|---|
| `traces:read` | query the trace store | `jaeger_trace_statistics`, `jaeger_slow_traces` |
| `services:read` | list services, which the probe uses | `jaeger_trace_statistics` |

Jaeger has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Times are microseconds since the epoch.** Seconds or milliseconds return an empty result rather than an error, which reads as a quiet period.
- **The query API is not versioned and is not a stability contract.** It is what the Jaeger UI uses, and it has changed shape between major releases.
- **Sampling happens at the client**, so a trace count here is a count of sampled traces and not of requests.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
