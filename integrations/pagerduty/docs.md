# PagerDuty

Who is being paged and for what: the incidents PagerDuty is holding, one incident's log, and the acknowledgement that stops the escalation clock.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | PagerDuty REST API token, user-scoped or account-scoped | yes | yes |

```bash
ninjasre integrations setup pagerduty
ninjasre integrations verify pagerduty
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

PagerDuty → Integrations → API Access Keys, or a user token

| Permission | What it grants | Without it |
|---|---|---|
| `incidents.read` | read incidents and their log entries | `pagerduty_incident_statistics`, `pagerduty_incident_timeline` |
| `incidents.write` | acknowledge an incident | `pagerduty_acknowledge_incident` |

PagerDuty has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Acknowledging stops the escalation clock.** It does not resolve the incident, and PagerDuty will re-escalate after the acknowledgement timeout unless somebody acts.
- **The `From` header is required for writes** and names the user the change is attributed to; an account token without it is refused.
- **Log entries are per incident**, so a timeline is one call per incident rather than part of the listing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
