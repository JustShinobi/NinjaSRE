# Opsgenie

Opsgenie alerts and their state: what is open, one alert's log, and the acknowledgement that stops the escalation.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | Opsgenie API key for an API integration with read and write access | yes | yes |

```bash
ninjasre integrations setup opsgenie
ninjasre integrations verify opsgenie
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `eu`.

## Permissions

Opsgenie → Settings → API key management

| Permission | What it grants | Without it |
|---|---|---|
| `read` | read alerts and their logs | `opsgenie_incident_statistics`, `opsgenie_incident_timeline` |
| `configuration access` | acknowledge an alert | `opsgenie_acknowledge_incident` |

Opsgenie has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The regional host differs between the US and EU accounts** and is not derivable from the key, so it is configuration.
- **Acknowledging is asynchronous.** The response is a request id and the alert changes state shortly afterwards, so an immediate re-read may still show it open.
- **Alert search is a query language, not parameters**, and an unquoted colon in a value is a syntax error that reads as an empty result.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
