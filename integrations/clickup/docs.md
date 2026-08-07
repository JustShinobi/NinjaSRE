# ClickUp

What ClickUp already tracks: the tasks in a list, in what status, and which are worth reading before another is created.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | ClickUp personal API token | yes | yes |
| `list_id` | ClickUp list id tasks are read from | no | yes |

```bash
ninjasre integrations setup clickup
ninjasre integrations verify clickup
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

ClickUp → Settings → Apps → API token

| Permission | What it grants | Without it |
|---|---|---|
| `tasks:read` | read tasks in the configured list | `clickup_issue_statistics`, `clickup_recent_issues` |
| `list:read` | read the list itself, which the probe uses | `clickup_issue_statistics` |

ClickUp has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The list id is part of the path** and is substituted by the proxy, so a capability cannot be pointed at another list.
- **Pages are fixed at 100 tasks** and there is no page-size parameter; the walk stops on a short page.
- **Statuses are per space and configurable**, so a status name that means 'done' in one list means nothing in another.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
