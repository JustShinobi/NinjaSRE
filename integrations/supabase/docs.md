# Supabase

The Supabase management API: which projects exist in an organisation and in what state, for the estates that run their Postgres there.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Supabase management API personal access token | yes | yes |
| `organisation` | Supabase organisation slug | no | no |

```bash
ninjasre integrations setup supabase
ninjasre integrations verify supabase
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Supabase → Account → Access Tokens

| Permission | What it grants | Without it |
|---|---|---|
| `projects:read` | list projects and their status | `supabase_session_statistics`, `supabase_slow_queries` |
| `organizations:read` | read organisations, which the probe uses | `supabase_session_statistics` |

Supabase has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **This is the management API, not the database.** Queries against the data live on the project's own PostgREST host and use a different key entirely.
- **There is no pagination**, so a large organisation returns everything in one response and the cap here is the only bound.
- **A personal access token carries the person's access**, so an offboarded engineer's token stops working without anything in NinjaSRE changing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
