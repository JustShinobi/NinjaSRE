# Bitbucket

What landed in a Bitbucket workspace: the repositories that changed recently and the pull requests merged into them.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Bitbucket username, or the email on an Atlassian account | yes | yes |
| `password` | App password with repository and pull-request read access | yes | yes |
| `workspace` | Bitbucket workspace slug | no | yes |

```bash
ninjasre integrations setup bitbucket
ninjasre integrations verify bitbucket
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Bitbucket → Personal settings → App passwords

| Permission | What it grants | Without it |
|---|---|---|
| `repository:read` | list repositories in the workspace | `bitbucket_change_statistics`, `bitbucket_recent_changes` |
| `pullrequest:read` | read pull requests on those repositories | `bitbucket_recent_changes` |

Bitbucket has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The workspace is part of the path** and is substituted by the proxy from the stored configuration, so a capability cannot be pointed at another workspace.
- **App passwords are being replaced by API tokens** on Atlassian accounts, and both still authenticate; the app password is what this schema describes.
- **`next` is a full URL rather than a token.** The client follows it as an absolute path, and the proxy's allow-list still applies.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
