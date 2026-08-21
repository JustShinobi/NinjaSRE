# incident.io

incident.io's record of what is happening: the open incidents, one incident's timeline, and the acknowledgement that says somebody is on it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | incident.io API key with incident read and write scopes | yes | yes |

```bash
ninjasre integrations setup incident_io
ninjasre integrations verify incident_io
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

incident.io → Settings → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their updates | `incident_io_incident_statistics`, `incident_io_incident_timeline` |
| `incidents:write` | post an incident update | `incident_io_acknowledge_incident` |

incident.io has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **incident.io has no acknowledgement primitive.** Posting an update is the closest equivalent and is what this integration's write capability does; it is visible to everyone on the incident and cannot be unsaid, only corrected.
- **Severity and status are separate.** A `live` incident may be any severity, and grouping by only one of them answers half the question.
- **Custom fields differ per organisation**, so anything beyond the built-in fields is not portable between deployments.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
