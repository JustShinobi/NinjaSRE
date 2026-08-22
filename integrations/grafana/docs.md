# Grafana

What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `endpoint` | Where your Grafana answers, scheme and port included | no | yes |
| `token` | Grafana service account token, with the Viewer role at minimum | yes | yes |
| `org` | Grafana organisation id, when the stack has more than one | no | no |

```bash
ninjasre integrations setup grafana
ninjasre integrations verify grafana
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

`endpoint` is the exception: it is not a credential. It goes to the
configuration tree, not the vault, which is where the credential proxy already
reads its egress allow-list from — declaring the address and permitting it are
one act.

Declared regions: `self-hosted`.

Grafana is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `grafana.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Administration → Users and access → Service accounts → Add service account token

| Permission | What it grants | Without it |
|---|---|---|
| `dashboards:read` | list dashboards and folders | `grafana_resource_inventory` |
| `annotations:read` | read the annotation timeline, including deploy markers | `grafana_recent_changes` |

Grafana has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Annotations are only as good as what writes them.** A stack whose deploy pipeline does not annotate has an empty change history here, and an empty answer is indistinguishable from nothing having been deployed.
- **Search is page-numbered and capped at 5,000 results by Grafana itself.** A stack with more dashboards than that cannot be fully enumerated in one call.
- **Service account tokens carry a role, not a scope list.** Viewer is enough for both capabilities here; anything less returns 403 on the first call.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
