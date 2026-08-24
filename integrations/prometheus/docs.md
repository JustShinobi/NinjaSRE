# Prometheus

PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.

## Setup

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `endpoint` | Where your Prometheus answers, scheme and port included | — | [HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/) |
| `token` | Bearer token accepted by whatever fronts Prometheus, which usually has no auth of its own | whatever your reverse proxy or ingress accepts | [Securing with a reverse proxy](https://prometheus.io/docs/guides/basic-auth/) |

Sources: both from Prometheus's own documentation. `token`'s guidance is
shared with Alertmanager's, because both ship no authentication of their own
and are fronted the same way.

```bash
ninjasre integrations setup prometheus
ninjasre integrations verify prometheus
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

`endpoint` is the exception: it is not a credential. It goes to the
configuration tree, not the vault, which is where the credential proxy already
reads its egress allow-list from — declaring the address and permitting it are
one act.

The token is optional because Prometheus ships no authentication of its own:
an install reached directly needs nothing here, and this field only matters
for whatever sits in front of it.

Declared regions: `self-hosted`.

Prometheus is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `prometheus.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Your reverse proxy, ingress, or Grafana Cloud access policy — Prometheus itself ships no authentication

| Permission | What it grants | Without it |
|---|---|---|
| `query` | evaluate PromQL over the stored series | `prometheus_metric_statistics` |
| `rules:read` | read alerting rules and their current state | `prometheus_active_alerts` |

Prometheus has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Prometheus does not paginate.** A range query returns every matching series in one response, so a query matching thousands is a query that has to be narrowed rather than paged.
- **A range query with too many points is refused**, with a message about the resolution rather than about the query. Widen the step before widening the window.
- **Local retention is usually days, not months.** Anything older lives in the remote-write target, which is a different integration.
- **Prometheus has no authentication of its own.** Whatever is in front of it is what the token authenticates against, and a deployment with nothing in front of it accepts any token, including a wrong one.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
