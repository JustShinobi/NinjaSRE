# Docker

The Docker Engine API: which containers exist and in what state, and the engine events that changed them.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts the Docker Engine API | yes | yes |

```bash
ninjasre integrations setup docker
ninjasre integrations verify docker
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Docker is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `docker.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your TLS-terminating proxy — the Engine API has no authentication of its own and must never be exposed without one

| Permission | What it grants | Without it |
|---|---|---|
| `containers:list` | list containers and their state | `docker_resource_inventory` |
| `events:read` | read the engine event stream | `docker_recent_changes` |

Docker has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The Engine API has no authentication.** Anything reachable on it can control the host, so this integration assumes a proxy in front and declares that host.
- **`/events` streams by default.** Bounded by `since` and `until` it answers once, which is the only form this client uses.
- **One engine, not a cluster.** A Swarm or Kubernetes estate is a different integration; this one sees the containers on the engine it is pointed at.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
