# Jira

What Jira already knows about a symptom: how many issues match, in what state, and which ones are worth reading before another is opened.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Atlassian account email | yes | yes |
| `password` | Atlassian API token, not the account password | yes | yes |
| `project` | Default project key searches are scoped to | no | no |

```bash
ninjasre integrations setup jira
ninjasre integrations verify jira
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `site`.

Jira is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `acme.atlassian.net`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

id.atlassian.com → Security → API tokens

| Permission | What it grants | Without it |
|---|---|---|
| `Browse Projects` | search and read issues in a project | `jira_issue_statistics`, `jira_recent_issues` |
| `read:jira-user` | read the token owner, which the probe uses | `jira_issue_statistics` |

Jira has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The site host is per customer** — `<site>.atlassian.net` — so there is no shared host to declare.
- **An API token carries the person's permissions.** A project they cannot browse is silently absent from results rather than refused.
- **JQL is validated server-side and a bad query is a 400** whose message names the clause, which is the useful part to surface.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
