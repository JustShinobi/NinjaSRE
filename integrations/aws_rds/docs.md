# AWS RDS

The RDS control plane: which database instances exist and in what state, and the events RDS recorded against them — failovers, restarts, parameter changes.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_rds
ninjasre integrations verify aws_rds
```

The prompt asks for each field the schema declares and writes the values
straight to the vault. Nothing is displayed back, and nothing reaches the agent:
a capability carries a handle and the credential proxy injects the real value at
the network edge.

Declared regions: `us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`, `eu-west-1`, `eu-west-2`, `eu-central-1`, `ap-south-1`, `ap-southeast-1`, `ap-southeast-2`, `ap-northeast-1`, `sa-east-1`.

## Permissions

IAM → Users → Security credentials, or the role your deployment assumes

| Permission | What it grants | Without it |
|---|---|---|
| `rds:DescribeDBInstances` | read instance state and configuration | `aws_rds_resource_inventory` |
| `rds:DescribeEvents` | read the failover, restart, and parameter-change history | `aws_rds_recent_changes` |

AWS RDS has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **RDS answers XML**, like the rest of the query-protocol services.
- **`DescribeEvents` keeps 14 days.** Anything older is gone, and the answer is an empty list rather than an error saying so.
- **This is the control plane, not the database.** Sessions, locks, and query plans live inside the engine and are reached with the engine's own integration.
- **Events are per source type.** Instance events and cluster events are separate listings, and a search that names neither returns both interleaved.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
