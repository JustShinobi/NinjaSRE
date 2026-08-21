# Datadog

Log search and aggregation, metric series, and monitor state. Datadog is the
reference integration for the ordinary case: a REST API, two header
credentials, and no vendor library in the dependency tree.

## Setup

Two credential fields are required and one is optional.

| Field | Where it comes from | Secret |
|---|---|---|
| `api_key` | Organisation Settings → API Keys | yes |
| `app_key` | Organisation Settings → Application Keys | yes |
| `site` | Which regional deployment your organisation is on | no |

```bash
ninjasre integrations setup datadog
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Neither key is ever displayed back, and neither reaches
the agent: a capability carries a handle and the credential proxy injects the
real values at the network edge.

`site` selects the base URL. Leave it blank for `datadoghq.com`; the other
declared sites are `datadoghq.eu`, `us3.datadoghq.com`, `us5.datadoghq.com`,
`ap1.datadoghq.com`, and `ddog-gov.com`. A site that is not one of those is
refused when it is entered, with the list, rather than producing requests the
proxy silently declines.

Check it before you need it:

```bash
ninjasre integrations verify datadog
```

## Permissions

Datadog's scopes live on the **application** key, not the API key. A correctly
pasted pair can still be missing a scope, and the symptom is a 403 during an
incident that reads like a network problem.

| Scope | What it grants | Without it |
|---|---|---|
| `logs_read_data` | Read log events and their aggregations | `datadog_log_statistics` and `datadog_sample_logs` cannot run |
| `monitors_read` | List monitors and their alerting state | The connectivity check and monitor reads fail |

Datadog has no endpoint that reports what a key is allowed to do, so
verification probes each scope by making the cheapest form of the read that
needs it. The verification output says so — a permission reported as present is
present *for that read*, which is what the capability needs it for.

Grant or change scopes on the application key in Organisation Settings →
Application Keys.

## Limitations

- **Retention bounds the investigation.** Logs are queryable for as long as
  your Datadog plan retains them, and a query reaching further back returns
  nothing rather than an error. Check the retention before concluding that
  something did not happen.
- **Aggregations may be sampled above a volume threshold** that depends on the
  plan. A count from `datadog_log_statistics` is exact for ordinary volumes and
  becomes an estimate for very large ones.
- **Sampling is capped at 20 lines per call** and the result says when more
  matched. A truncated sample read as a complete one is how an investigation
  concludes wrongly.
- **Rate limits are per organisation, not per team.** Several teams
  investigating at once share one budget, and the client honours Datadog's own
  `Retry-After` up to a ceiling before giving up rather than sleeping through
  the investigation.
- **Metrics and monitors are read; nothing here writes.** Muting a monitor or
  posting an event is a change, and a change needs an approval gate and a
  rollback plan, which is a different kind of capability.
