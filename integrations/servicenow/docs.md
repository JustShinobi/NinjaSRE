# ServiceNow

ServiceNow incident records: what is open, one incident's work notes, and the update that records an automated investigation.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | ServiceNow integration user id | yes | yes |
| `password` | That user's password | yes | yes |

```bash
ninjasre integrations setup servicenow
ninjasre integrations verify servicenow
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `instance`.

ServiceNow is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `acme.service-now.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

ServiceNow → User Administration → Users, on the integration account

| Permission | What it grants | Without it |
|---|---|---|
| `itil` | read and update incident records | `servicenow_incident_statistics`, `servicenow_incident_timeline`, `servicenow_acknowledge_incident` |
| `rest_service` | reach the Table API at all | `servicenow_incident_statistics`, `servicenow_incident_timeline`, `servicenow_acknowledge_incident` |

ServiceNow has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The instance host is per customer** — `<instance>.service-now.com` — so there is no shared host to declare.
- **The Table API returns display values or raw values, not both.** `sysparm_display_value=true` gives readable priorities and loses the numeric ones a comparison would want.
- **A basic-auth integration user should not be a person.** ServiceNow ties audit records to the authenticating user, and a shared human account makes every automated change look manual.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
