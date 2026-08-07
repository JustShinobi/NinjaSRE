# Azure Monitor

KQL against a Log Analytics workspace: the shape of what a query matched, and the records behind it, for the estates whose telemetry lands in Azure.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | Azure AD access token for the Log Analytics API audience | yes | yes |
| `workspace` | Log Analytics workspace id | no | yes |

```bash
ninjasre integrations setup azure_monitor
ninjasre integrations verify azure_monitor
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `global`.

## Permissions

Azure Portal → App registrations → your service principal → Certificates & secrets, exchanged for a token against https://api.loganalytics.io

| Permission | What it grants | Without it |
|---|---|---|
| `Log Analytics Reader` | run KQL against the workspace | `azure_monitor_log_statistics`, `azure_monitor_sample_logs` |
| `workspace:metadata` | read the workspace schema, which the probe uses | `azure_monitor_log_statistics` |

Azure Monitor has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The workspace id is part of the path** and is substituted by the proxy from the stored configuration, so a capability cannot be pointed at another workspace.
- **The answer is a table, not a list of records.** Rows and columns arrive separately, so a per-row grouping needs the column names — which is why the records here are the tables and the useful grouping is by table name.
- **Access tokens expire in an hour.** The stored credential is a token rather than a secret, so a deployment refreshes it or verification starts failing.
- **Query limits are 500,000 rows or 64 MB**, whichever comes first, and exceeding either is a partial answer with a warning rather than an error.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
