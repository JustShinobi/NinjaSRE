# Google Docs

What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | OAuth access token for a service account with Drive read access | yes | yes |

```bash
ninjasre integrations setup google_docs
ninjasre integrations verify google_docs
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

IAM & Admin → Service Accounts → Keys, exchanged for an access token with the drive.readonly scope

| Permission | What it grants | Without it |
|---|---|---|
| `drive.readonly` | list and read document metadata | `google_docs_issue_statistics`, `google_docs_recent_issues` |
| `drive.about.get` | read the token's own account, which the probe uses | `google_docs_issue_statistics` |

Google Docs has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **A service account sees only what is shared with it**, and domain-wide delegation is a separate decision with a much wider blast radius.
- **`fields` is mandatory in practice.** Without it Drive returns a minimal projection that omits the modification time, which is the field that matters.
- **Access tokens expire in an hour**, so the stored credential is refreshed rather than being long-lived.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
