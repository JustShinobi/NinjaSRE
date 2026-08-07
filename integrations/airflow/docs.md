# Airflow

Airflow's scheduler state: which DAG runs are in which state, and the task instances that failed, which is where a data-freshness incident starts.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `username` | Airflow user with the Viewer role at minimum | yes | yes |
| `password` | That user's password, or the token your auth backend issues | yes | yes |

```bash
ninjasre integrations setup airflow
ninjasre integrations verify airflow
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `self-hosted`.

Airflow is self-hosted, so NinjaSRE cannot know where yours is. The
documented default is `airflow.example.com`; a deployment reaching its own
endpoint declares it, and the proxy then permits exactly that host and no
other. The allow-list is still a declaration — it is just made by the
operator rather than by this repository.

## Permissions

Airflow → Security → List Users, or whichever auth backend your webserver uses

| Permission | What it grants | Without it |
|---|---|---|
| `can_read on DAG Runs` | list DAG runs and their state | `airflow_pipeline_health`, `airflow_recent_failures` |
| `can_read on Task Instances` | read the tasks behind a failed run | `airflow_recent_failures` |

Airflow has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **The stable REST API is Airflow 2.** A 1.10 deployment has the experimental API at a different path and a different shape.
- **Basic auth depends on the auth backend.** A deployment using an identity provider rejects it, and the token that works instead is deployment-specific.
- **`~` means all DAGs** and is a real path segment, which is unusual enough to be worth stating: `/dags/~/dagRuns` is the cross-DAG listing.
- **Statistics are computed here rather than by the vendor**, over the capped page the query returned, and the result says so. A distribution over a capped sample and one over everything are different claims, and only one of them is what this returns.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
