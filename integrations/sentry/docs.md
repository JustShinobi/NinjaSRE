# Sentry

Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Sentry auth token with project:read and event:read | yes | yes |
| `organisation` | Sentry organisation slug | no | yes |
| `project` | Default project slug to search | no | no |

```bash
ninjasre integrations setup sentry
ninjasre integrations verify sentry
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us`, `de`, `self-hosted`.

## Permissions

Settings → Developer Settings → Auth Tokens, or an organisation token

| Permission | What it grants | Without it |
|---|---|---|
| `project:read` | list projects and their issues | `sentry_log_statistics`, `sentry_sample_logs` |
| `event:read` | read the events behind an issue | `sentry_sample_logs` |

Sentry has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The organisation slug is part of the path**, and the proxy substitutes it from the stored configuration — so the client never carries it and a token scoped to one organisation cannot be pointed at another by an argument.
- **Sentry pages by an opaque cursor in a Link header**, and this client reads only the body. A result larger than one page is reported as truncated rather than silently shortened.
- **`statsPeriod` and an explicit window are mutually exclusive.** Sending both is a 400, and the message names neither.
- **Issue counts are per issue, not per event.** Ten thousand events in one issue is one row here, which is usually what you want and occasionally is not.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
