# Argo CD

What Argo CD has actually applied: which applications are synced and healthy, and the ones that are not.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Argo CD API token for a project-scoped account | yes | yes |

```bash
ninjasre integrations setup argocd
ninjasre integrations verify argocd
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Argo CD is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `argocd.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Settings → Accounts → generate token, or `argocd account generate-token`

| Permission | What it grants | Without it |
|---|---|---|
| `applications, get` | read application state and sync status | `argocd_pipeline_statistics`, `argocd_failed_runs` |
| `account, get` | read the account, which the probe uses | `argocd_pipeline_statistics` |

Argo CD has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **Argo CD reports desired versus live, not a deploy log.** 'Synced' means the cluster matches Git; it does not mean the change worked.
- **RBAC is per project.** A token scoped to one project sees an empty application list for the others rather than a 403.
- **There is no pagination.** Every matching application comes back in one response, and the cap here is the only bound.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
