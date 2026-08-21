# GitLab

What landed in a GitLab project: the commits on a branch and the merge requests recently merged into it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `api_key` | GitLab personal, project, or group access token with read_api | yes | yes |
| `project_id` | Default project id or URL-encoded path | no | no |

```bash
ninjasre integrations setup gitlab
ninjasre integrations verify gitlab
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `gitlab.com`, `self-managed`.

## Permissions

GitLab → Settings → Access Tokens, with the read_api scope

| Permission | What it grants | Without it |
|---|---|---|
| `read_api` | read projects, commits, and merge requests | `gitlab_change_statistics`, `gitlab_recent_changes` |
| `read_user` | read the token's own identity, which the probe uses | `gitlab_change_statistics` |

GitLab has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **GitLab pages by page number and reports the total in headers**, which this client does not read. A walk that reaches its page bound reports truncation rather than claiming completeness.
- **A project token is scoped to one project** and its listings ignore anything else, which is safer and occasionally surprising.
- **`updated_after` is ISO 8601 and is the only reliable time filter** on merge requests; `created_after` misses a request opened before the window and merged inside it.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
