# RabbitMQ

RabbitMQ's management API: which queues exist and how deep they are, which is the first question of every message-backlog incident.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | RabbitMQ management user with the monitoring tag | yes | yes |
| `password` | That user's password | yes | yes |
| `vhost` | Virtual host to read, defaulting to / | no | no |

```bash
ninjasre integrations setup rabbitmq
ninjasre integrations verify rabbitmq
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

RabbitMQ is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `rabbitmq.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

RabbitMQ management UI → Admin → Users, with the `monitoring` tag

| Permission | What it grants | Without it |
|---|---|---|
| `monitoring` | read queues, overview, and node statistics | `rabbitmq_pipeline_health`, `rabbitmq_recent_failures` |
| `management` | reach the management plugin at all | `rabbitmq_pipeline_health`, `rabbitmq_recent_failures` |

RabbitMQ has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The management plugin has to be enabled.** Without it the API is not there at all and every call is a connection refused rather than a 404.
- **Listing every queue on a large broker is expensive**, which is what the `columns` parameter is for: it is not an optimisation, it is what keeps the call from affecting the broker.
- **AMQP itself is a binary protocol** and is not reachable through an HTTP credential proxy. What is reachable is the management plugin.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
