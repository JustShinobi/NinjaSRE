# AWS S3

What is in the bucket this team configured: the objects and their storage class, and the version history, which is the closest S3 has to a change log.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |
| `bucket` | The bucket this integration reads | no | yes |

```bash
ninjasre integrations setup aws_s3
ninjasre integrations verify aws_s3
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
| `s3:ListBucket` | list the objects in the configured bucket | `aws_s3_resource_inventory` |
| `s3:ListBucketVersions` | list object versions, which is what makes a change history | `aws_s3_recent_changes` |

AWS S3 has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **S3 answers XML**, and this client reads it into the same record shape the rest of the catalogue uses.
- **Version history exists only on a versioned bucket.** On one that is not, the second capability returns nothing, which reads exactly like nothing having changed.
- **Listing is eventually consistent for deletes.** An object deleted seconds ago may still appear, which matters when the question is whether something is gone.
- **One bucket per configured integration.** Reading a second bucket is a second credential entry, deliberately — a capability that could be pointed anywhere is one lookup away from reading somebody else's data.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
