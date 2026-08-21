# Blameless

Blameless's incident record: what is open, one incident's events, and the update that says an automated investigation is under way.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Blameless API token for a service account | yes | yes |

```bash
ninjasre integrations setup blameless
ninjasre integrations verify blameless
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `tenant`.

Blameless is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `acme.blameless.io`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Blameless → Settings → API tokens

| Permission | What it grants | Without it |
|---|---|---|
| `incidents:read` | read incidents and their events | `blameless_incident_statistics`, `blameless_incident_timeline` |
| `incidents:write` | post an event onto an incident | `blameless_acknowledge_incident` |

Blameless has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Blameless is per-tenant.** The host is `<tenant>.blameless.io` and there is no shared one, so the host is configuration a deployment declares.
- **Posting an event is the closest thing to an acknowledgement.** Blameless models response state through roles rather than an acknowledged flag.
- **Retrospective data is a separate surface** and is not part of the incident listing here.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
