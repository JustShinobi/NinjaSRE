# GitHub

What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.

## Setup

Secret and required status are declared once, in this package's `schema.py`;
this table does not repeat them. It carries what `schema.py` does not show in a
browsable form: what each field is, the minimum permission it needs when it is
secret, and a guide to producing it.

| Field | What it is | Minimum permission | Guide |
|---|---|---|---|
| `endpoint` | Only for GitHub Enterprise Server — https://github.acme.example/api/v3 | — | [About GitHub Enterprise Server](https://docs.github.com/en/enterprise-server@latest/admin/overview/about-github-enterprise-server) |
| `token` | GitHub token — a fine-grained personal access token or an app installation token | Repository permissions: Contents (read-only) and Pull requests (read-only) | [Managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| `owner` | Default organisation or user the repositories belong to | — | [About organizations](https://docs.github.com/en/organizations/collaborating-with-groups-in-organizations/about-organizations) |

Sources: all three from GitHub's own documentation, current as of this feature.

```bash
ninjasre integrations setup github
ninjasre integrations verify github
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

`endpoint` goes to the configuration tree rather than the vault — it is where
the credential proxy reads its egress allow-list from, and it stays empty for
github.com.

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
