# MongoDB Atlas

The Atlas control plane: which clusters and processes exist in a project, and the slow-query entries Atlas's performance advisor has collected.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Atlas API public key | yes | yes |
| `password` | Atlas API private key | yes | yes |
| `group` | Atlas project (group) id | no | yes |

```bash
ninjasre integrations setup mongodb_atlas
ninjasre integrations verify mongodb_atlas
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Atlas → Organization Access Manager → API Keys, with Project Read Only

| Permission | What it grants | Without it |
|---|---|---|
| `Project Read Only` | read processes and clusters in the project | `mongodb_atlas_session_statistics`, `mongodb_atlas_slow_queries` |
| `Project Monitoring Admin` | read process measurements and the performance advisor | `mongodb_atlas_slow_queries` |

MongoDB Atlas has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Atlas API keys use HTTP digest authentication in the documentation** and accept basic on the v2 endpoints. The v2 endpoints are what this integration uses.
- **The project id is part of the path** and is substituted by the proxy, so a key spanning several projects still reads only the configured one.
- **This is the control plane, not the database.** Current operations inside a deployment need a driver connection, which is not something an HTTP proxy can carry.
- **API keys are IP-access-listed by default**, so a proxy egress address that is not on the list is refused before any permission is considered.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
