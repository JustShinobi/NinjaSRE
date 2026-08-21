# AWS ELB

Elastic Load Balancing state: which load balancers exist and in what state, and the target groups behind them.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_elb
ninjasre integrations verify aws_elb
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
| `elasticloadbalancing:DescribeLoadBalancers` | read load balancer state and scheme | `aws_elb_resource_inventory` |
| `elasticloadbalancing:DescribeTargetGroups` | read the target groups behind each load balancer | `aws_elb_recent_changes` |

AWS ELB has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **This is ELBv2** — application and network load balancers. A classic load balancer is a different API and is not covered.
- **Target *health* is per target group**, one call each, and is not in either listing here. What is here is which target groups exist.
- **Request and error metrics are CloudWatch**, which is the `aws` integration.
- **ELB answers XML**, like the rest of the query-protocol services.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
