# AWS ECS

The ECS control plane: which clusters this account runs and which task definitions have been registered, which is where a deployment shows up.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_ecs
ninjasre integrations verify aws_ecs
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
| `ecs:ListClusters` | list the clusters in this account and region | `aws_ecs_resource_inventory` |
| `ecs:ListTaskDefinitions` | list registered task definitions, newest first | `aws_ecs_recent_changes` |

AWS ECS has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **ECS uses the JSON-1.1 protocol**, so every call is a POST to `/` with the operation in an `X-Amz-Target` header rather than in the path.
- **List operations answer with ARNs, not objects.** Each ARN is recorded as one entry; the detail behind it needs a `Describe` call per ARN.
- **A new task definition revision is the closest thing ECS has to a deploy marker.** Which service adopted it is a `DescribeServices` question.
- **Task-level failures appear in service events**, which are per service and not in either listing here.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
