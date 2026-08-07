# BigQuery

BigQuery job state for a project: what is running or queued, and the jobs that took longest, which is where a data-freshness incident usually starts.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `token` | OAuth access token for a service account with BigQuery job access | yes | yes |
| `project` | Google Cloud project id | no | yes |

```bash
ninjasre integrations setup bigquery
ninjasre integrations verify bigquery
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
| `bigquery.jobs.list` | list jobs in the project | `bigquery_session_statistics`, `bigquery_slow_queries` |
| `bigquery.jobs.get` | read a job's statistics and errors | `bigquery_slow_queries` |

BigQuery has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **`allUsers=true` needs a project-level role.** Without it the listing shows only the service account's own jobs, which on a shared project reads as an idle warehouse.
- **Job history is six months** and is per project and location. A job run in another location is invisible without naming it.
- **`projection=full` is much more expensive** and is why the two capabilities use different projections.
- **A failed job's error is in `status.errorResult`**, not in the HTTP status. The call succeeds and the job did not.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
