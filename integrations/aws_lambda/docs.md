# AWS Lambda

The Lambda control plane: which functions exist, on which runtime and memory setting, and when each was last modified.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_lambda
ninjasre integrations verify aws_lambda
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
| `lambda:ListFunctions` | list the functions in this region | `aws_lambda_resource_inventory`, `aws_lambda_recent_changes` |
| `lambda:GetFunctionConfiguration` | read a function's runtime, memory, and last modification | `aws_lambda_recent_changes` |

AWS Lambda has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **`LastModified` is the closest Lambda has to a change history.** Who changed a function and why is a CloudTrail question, not a Lambda one.
- **Invocation metrics and logs are CloudWatch**, which is the `aws` integration. Lambda itself knows about configuration.
- **Listing is per region and paged by an opaque marker** that expires, so a walk that is paused and resumed starts again.
- **A deprecated runtime is visible here before it is a problem**, which is the cheapest use of the grouping this capability offers.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
