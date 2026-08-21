# Amplitude

Amplitude's product analytics: how user-facing event volume moved during a window, and which annotations mark what changed.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Amplitude API key | yes | yes |
| `password` | Amplitude secret key | yes | yes |

```bash
ninjasre integrations setup amplitude
ninjasre integrations verify amplitude
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `eu`.

## Permissions

Amplitude → Settings → Projects → your project → General

| Permission | What it grants | Without it |
|---|---|---|
| `events:read` | run event segmentation queries | `amplitude_metric_statistics` |
| `annotations:read` | read chart annotations | `amplitude_active_alerts` |

Amplitude has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Amplitude is about users, not systems.** A drop here is a symptom whose cause lives in one of the other integrations, and treating it as a cause is the most common way to misread it.
- **Event data is delayed** by minutes to an hour depending on ingest, so an incident investigated immediately sees an incomplete window.
- **Dates are `YYYYMMDD`**, not ISO 8601, which is unusual enough to be the first thing to check when a window returns nothing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
