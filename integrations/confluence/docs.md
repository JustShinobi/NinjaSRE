# Confluence

What has already been written down: the Confluence pages matching a search, and the ones most recently changed.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Atlassian account email | yes | yes |
| `password` | Atlassian API token, not the account password | yes | yes |
| `space` | Default space key searches are scoped to | no | no |

```bash
ninjasre integrations setup confluence
ninjasre integrations verify confluence
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `site`.

Confluence is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `acme.atlassian.net`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

id.atlassian.com → Security → API tokens

| Permission | What it grants | Without it |
|---|---|---|
| `read:confluence-content.all` | search and read pages | `confluence_issue_statistics`, `confluence_recent_issues` |
| `read:confluence-space.summary` | list spaces, which the probe uses | `confluence_issue_statistics` |

Confluence has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The site host is per customer** — `<site>.atlassian.net` — so there is no shared host to declare.
- **A runbook found here is what somebody wrote, not what is true now.** Its last modification date is part of the evidence and belongs in any finding that cites it.
- **CQL's `text ~` operator is a full-text match** and behaves differently from Jira's JQL despite the similar name.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
