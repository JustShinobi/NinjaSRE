# Azure SQL

Azure SQL through Resource Manager: which databases exist in a subscription and in what state, and their recent service-level events.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Azure AD access token for the management API audience | yes | yes |
| `subscription` | Azure subscription id | no | yes |

```bash
ninjasre integrations setup azure_sql
ninjasre integrations verify azure_sql
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
| `Microsoft.Sql/servers/read` | list logical servers | `azure_sql_session_statistics` |
| `Microsoft.Sql/servers/databases/read` | read database state and service tier | `azure_sql_slow_queries` |

Azure SQL has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **This is the control plane.** Sessions, blocking, and query plans live inside the database and are reached over TDS, which an HTTP proxy cannot carry.
- **Every endpoint needs its own `api-version`**, and a missing one is a 400 that reads like a malformed request.
- **Access tokens expire in an hour**, so the stored credential is refreshed rather than being long-lived.
- **Serverless databases pause.** A paused database reports a state that is not a failure and often looks like one.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
