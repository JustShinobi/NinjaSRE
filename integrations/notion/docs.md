# Notion

What the team has written in Notion: the pages matching a search, and the ones most recently edited.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Notion internal integration secret | yes | yes |
| `api_version` | Notion API version, sent on every call | yes | yes |

```bash
ninjasre integrations setup notion
ninjasre integrations verify notion
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

notion.so/my-integrations → your integration → Internal Integration Secret

| Permission | What it grants | Without it |
|---|---|---|
| `read content` | search and read pages the integration is shared with | `notion_issue_statistics`, `notion_recent_issues` |
| `read user information` | read the bot user, which the probe uses | `notion_issue_statistics` |

Notion has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **An integration only sees pages explicitly shared with it.** An empty search result usually means nothing was shared rather than that nothing exists, and the two are indistinguishable from the API.
- **`Notion-Version` is required on every request** and is stored as a configuration field rather than hard-coded, because a version bump is a deployment decision.
- **Search does not match page body reliably** — it is optimised for titles — so a runbook whose title does not mention the symptom will not be found.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
