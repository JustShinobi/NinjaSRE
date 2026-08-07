# SigNoz

SigNoz's span store: where latency and errors concentrate for a service, and the slowest traces behind that concentration.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | SigNoz API key for the workspace holding this service's telemetry | yes | yes |

```bash
ninjasre integrations setup signoz
ninjasre integrations verify signoz
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

SigNoz is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `signoz.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

SigNoz → Settings → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `traces:read` | query the span store | `signoz_trace_statistics`, `signoz_slow_traces` |
| `version:read` | read the build version, which the probe uses | `signoz_trace_statistics` |

SigNoz has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **SigNoz is usually self-hosted**, so the host is configuration and the API version differs between releases more than a SaaS vendor's would.
- **Times are Unix milliseconds.** Seconds are accepted and mean 1970, which returns an empty result rather than an error.
- **Span sampling is configured at the collector**, so a count here is a count of what was sampled.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
