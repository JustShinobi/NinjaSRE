# Alertmanager

What Prometheus Alertmanager is currently holding: which alerts are firing, how they are grouped, and which are silenced rather than resolved.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `endpoint` | Where your Alertmanager answers, scheme and port included | no | yes |
| `token` | Bearer token accepted by whatever fronts Alertmanager | yes | no |

```bash
ninjasre integrations setup alertmanager
ninjasre integrations verify alertmanager
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

`endpoint` is the exception: it is not a credential. It goes to the
configuration tree, not the vault, which is where the credential proxy already
reads its egress allow-list from — declaring the address and permitting it are
one act.

The token is optional because Alertmanager ships no authentication of its own:
an install reached directly needs nothing here, and this field only matters
for whatever sits in front of it.

Declared regions: `self-hosted`.

Alertmanager is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `alertmanager.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Your reverse proxy or ingress — Alertmanager ships no authentication of its own

| Permission | What it grants | Without it |
|---|---|---|
| `alerts:read` | read the alerts Alertmanager is holding | `alertmanager_incident_statistics`, `alertmanager_incident_timeline` |
| `silences:write` | create a silence, which is how it acknowledges | `alertmanager_acknowledge_incident` |

Alertmanager has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Alertmanager does not paginate.** Every matching alert comes back in one response; a deployment with thousands firing gets thousands, and the cap here is the only bound.
- **Acknowledging is a silence with an end time.** Alertmanager has no separate acknowledgement, so an unbounded silence is how an alert is lost — the capability always sets one.
- **A silence matches labels, not an alert instance.** A matcher wider than intended silences alerts nobody looked at.
- **Alertmanager ships no authentication.** Whatever fronts it is what the token authenticates against.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
