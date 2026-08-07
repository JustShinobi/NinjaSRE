# AWS EC2

EC2 instance state for a region: how many instances are in which state, and the instances themselves with their type, zone, and launch time.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_ec2
ninjasre integrations verify aws_ec2
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
| `ec2:DescribeInstanceStatus` | read instance state and any scheduled events | `aws_ec2_resource_inventory` |
| `ec2:DescribeInstances` | read instance detail and tags | `aws_ec2_recent_changes` |

AWS EC2 has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **EC2 answers XML.** It has no JSON dialect to ask for, so the client parses XML into the same record shape everything else here uses.
- **EC2 has no change history of its own.** `aws_cloudtrail` is the integration that answers 'who changed this and when'; the second capability here reads the current instances, including their launch times.
- **`DescribeInstances` returns nested elements**, so a record here may be a reservation, an instance, or a tag. Grouping by `instanceState.name` is what makes the count mean instances.
- **Describe calls are rate-limited per account, not per key.** Several investigations at once share one budget.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
