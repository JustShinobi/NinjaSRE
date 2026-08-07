# GitHub

What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | GitHub token — a fine-grained personal access token or an app installation token | yes | yes |
| `owner` | Default organisation or user the repositories belong to | no | no |

```bash
ninjasre integrations setup github
ninjasre integrations verify github
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `github.com`, `enterprise`.

## Permissions

GitHub → Settings → Developer settings → Personal access tokens, with Contents and Pull requests read access

| Permission | What it grants | Without it |
|---|---|---|
| `contents:read` | search and read commits in a repository | `github_change_statistics` |
| `pull_requests:read` | search and read pull requests | `github_recent_changes` |

GitHub has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Search is rate-limited far more tightly than the rest of the API** — 30 requests a minute rather than 5,000 an hour — and the limit is per token, so several investigations at once share it.
- **Search indexes lag** by up to a minute, so a commit pushed during an incident may not be findable yet. The commits endpoint on a specific repository does not lag and is the fallback.
- **A fine-grained token is scoped to specific repositories.** One that cannot see the repository returns an empty result rather than a 403.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
