# Google Cloud

The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | OAuth access token for a service account with the viewer roles | yes | yes |
| `project` | Google Cloud project id | no | yes |

```bash
ninjasre integrations setup gcp
ninjasre integrations verify gcp
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

IAM & Admin → Service Accounts → Keys, exchanged for an access token against oauth2.googleapis.com

| Permission | What it grants | Without it |
|---|---|---|
| `cloudasset.assets.listResource` | list the resources in the configured project | `gcp_resource_inventory`, `gcp_recent_changes` |
| `cloudasset.assets.searchAllResources` | read a resource's state at a point in time | `gcp_recent_changes` |

Google Cloud has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The project is part of the path** and is substituted by the proxy from the stored configuration, so a capability cannot be pointed at another project.
- **Cloud Asset Inventory has to be enabled** on the project, and it is not by default. Without it the answer is a 403 naming the API rather than the permission.
- **Access tokens expire in an hour.** The stored credential is a token rather than a key, so a deployment refreshes it or verification starts failing.
- **Logs are Cloud Logging, which is a different API.** Asset inventory answers what exists; it does not answer what a service printed.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
