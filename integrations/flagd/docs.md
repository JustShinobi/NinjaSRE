# flagd

OpenFeature's flagd: which feature flags this deployment is serving and in what state, which is the change history nothing else records.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Bearer token accepted by whatever fronts flagd | yes | yes |

```bash
ninjasre integrations setup flagd
ninjasre integrations verify flagd
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

flagd is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `flagd.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

your reverse proxy or service mesh — flagd's evaluation API has no authentication of its own

| Permission | What it grants | Without it |
|---|---|---|
| `evaluation:resolve` | resolve every flag for a context | `flagd_resource_inventory`, `flagd_recent_changes` |
| `healthz` | read liveness, which the connectivity probe uses | `flagd_resource_inventory` |

flagd has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **A flag change is a production change that no deployment pipeline records.** That is the whole argument for this integration, and it is also why a flag resolved here is resolved for the *empty* context rather than for a user.
- **flagd's primary interface is gRPC**; the connect-protocol HTTP endpoints are what an HTTP credential proxy can reach, and a deployment serving gRPC only is not reachable.
- **flagd has no authentication of its own.** Whatever fronts it is what the token authenticates against.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
