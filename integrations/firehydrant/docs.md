# FireHydrant

FireHydrant's incident record: what is active, one incident's events, and the note that says an automated investigation has started.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | FireHydrant bot token or personal API key | yes | yes |

```bash
ninjasre integrations setup firehydrant
ninjasre integrations verify firehydrant
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

FireHydrant → Settings → API keys

| Permission | What it grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their events | `firehydrant_incident_statistics`, `firehydrant_incident_timeline` |
| `incidents:write` | post a note onto an incident | `firehydrant_acknowledge_incident` |

FireHydrant has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Milestones, not statuses.** FireHydrant models progress as milestones — `started`, `identified`, `mitigated`, `resolved` — and filtering by the wrong vocabulary returns nothing rather than an error.
- **A note is not an acknowledgement.** FireHydrant has no acknowledge primitive, and the note is what this integration's write capability posts.
- **Severity names are configurable per organisation**, so `SEV1` in one deployment may be `Critical` in another.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
