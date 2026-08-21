# AWS EKS

The EKS control plane: which clusters this account runs, their version and status, and the cluster updates that have been applied to them.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_eks
ninjasre integrations verify aws_eks
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
| `eks:ListClusters` | list the clusters in this account and region | `aws_eks_resource_inventory`, `aws_eks_recent_changes` |
| `eks:DescribeCluster` | read a cluster's version, endpoint, and status | `aws_eks_recent_changes` |

AWS EKS has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **EKS answers a list operation with names, not objects.** Each name is recorded as one entry so it can be counted and reported; the detail behind a name needs `DescribeCluster`, which is a per-cluster call rather than a listing.
- **Clusters are per region.** A cluster in `eu-west-1` is invisible to a client built for `us-east-1`, and the answer is an empty list rather than an error.
- **What runs *inside* a cluster is the `kubernetes` integration.** EKS knows about the control plane and nothing about a pod.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
