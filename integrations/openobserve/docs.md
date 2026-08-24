# OpenObserve

SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.

## Setup

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `endpoint` | Where your OpenObserve answers, scheme and port included | — | [OpenObserve docs](https://openobserve.ai/docs/) |
| `username` | OpenObserve user email | `streams:read` | [OpenObserve docs](https://openobserve.ai/docs/) |
| `password` | That user's password or token | `streams:read` | [OpenObserve docs](https://openobserve.ai/docs/) |
| `organisation` | OpenObserve organisation | — | [OpenObserve docs](https://openobserve.ai/docs/) |

Sources: OpenObserve's own documentation site; it has no stable deep link per
field, so all four point at the same entry point rather than at a guessed
anchor. `username` and `password` are Basic Auth, checked as one pair — the
account they identify together is what carries `streams:read`, not either
field alone.

The endpoint goes to the configuration tree rather than the vault — it is not
part of the credential, and it is where the credential proxy reads its egress
allow-list from, so declaring the address and permitting it stay one act.

```bash
ninjasre integrations setup openobserve
ninjasre integrations verify openobserve
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

OpenObserve is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `openobserve.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

OpenObserve → Settings → Users, or the token issued for that user

| Permission | What it grants | Without it |
|---|---|---|
| `streams:read` | search the streams this user can see | `openobserve_log_statistics`, `openobserve_sample_logs` |
| `health:read` | read health, which the connectivity probe uses | `openobserve_log_statistics` |

OpenObserve has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The organisation is part of the path.** A user in two organisations needs two credential entries, one per organisation.
- **Times are microseconds since the epoch**, not seconds or milliseconds, which is unusual enough to be the first thing to check when a window returns nothing.
- **SQL, not a log query language.** The stream is the table name, and a `SELECT *` without a `WHERE` scans the stream.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
