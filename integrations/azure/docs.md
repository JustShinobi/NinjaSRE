# Azure

The Azure Resource Manager control plane: what exists in a subscription, and the activity log entries that changed it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Azure AD access token for the management API audience | yes | yes |
| `subscription` | Azure subscription id | no | yes |

```bash
ninjasre integrations setup azure
ninjasre integrations verify azure
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Azure Portal → App registrations → your service principal, exchanged for a token against https://management.azure.com

| Permission | What it grants | Without it |
|---|---|---|
| `Microsoft.Resources/subscriptions/resources/read` | list resources | `azure_resource_inventory` |
| `Microsoft.Insights/eventtypes/values/read` | read the activity log, which is the change history | `azure_recent_changes` |

Azure has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The subscription is part of the path** and is substituted by the proxy, so a capability cannot be pointed at another subscription.
- **Every endpoint needs its own `api-version`**, and they differ per provider. A missing or wrong one is a 400 that reads like a malformed request.
- **The activity log keeps 90 days.** Anything older needs a diagnostic setting that exports it somewhere, which is a different integration.
- **Access tokens expire in an hour**, so the stored credential is refreshed rather than being a long-lived secret.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
