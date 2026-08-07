# New Relic

NRQL over New Relic's telemetry, and the alert violations currently open, for the accounts whose metrics and events live there.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | New Relic user API key, which is the one that can run NRQL | yes | yes |
| `account` | New Relic account id, required by every NRQL query | no | no |

```bash
ninjasre integrations setup new_relic
ninjasre integrations verify new_relic
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `eu`.

## Permissions

one.newrelic.com → API keys → Create a key, of type User

| Permission | What it grants | Without it |
|---|---|---|
| `apm:read` | read application summaries and their health | `new_relic_metric_statistics` |
| `alerts:read` | read open alert violations | `new_relic_active_alerts` |

New Relic has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **This reads the REST v2 API rather than NerdGraph.** NRQL lives in NerdGraph and needs the account id inside the GraphQL document, which is configuration a client holding no credential cannot see — so what is reachable here is the application summary and the alert violations, both of which answer 'what is unhealthy'.
- **Application summaries are what the agent reported**, so a service with no APM agent is invisible rather than healthy.
- **Data retention differs per event type** and per subscription, and a query reaching past it returns nothing rather than an error.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
