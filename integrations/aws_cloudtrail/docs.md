# AWS CloudTrail

Who changed what in this AWS account, and when. The change history most incidents turn out to need and most investigations reach for too late.

## Setup

| Field | Where it comes from | Secret | Required |
|---|---|---|---|
| `access_key_id` | AWS access key id, or the one an assumed role issued | yes | yes |
| `secret_access_key` | The secret half of the key pair. Never leaves the proxy | yes | yes |
| `session_token` | Session token, for temporary credentials from STS | yes | no |
| `region` | Default region for signing and endpoint selection | no | no |

```bash
ninjasre integrations setup aws_cloudtrail
ninjasre integrations verify aws_cloudtrail
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
| `cloudtrail:LookupEvents` | read the management-event history | `aws_cloudtrail_resource_inventory`, `aws_cloudtrail_recent_changes` |

AWS CloudTrail has no endpoint that reports what a credential is allowed to do,
so verification probes each permission by making the cheapest form of the read
that needs it. A permission reported as present is present *for that read*,
which is what the capability needs it for.

## Limitations

- **`LookupEvents` covers management events for 90 days**, and only management events. Data events — object reads, function invocations — are not in it whatever the trail configuration says.
- **Events appear with a delay**, typically minutes. An incident investigated immediately may be looking at a window CloudTrail has not finished writing.
- **Lookup is per region.** A change made in another region is invisible here, and the answer is an empty list rather than a redirect.
- **One lookup attribute at a time.** CloudTrail refuses two, so narrowing by both user and event name takes two calls and an intersection.
- **Nothing here writes unless the capability says so.** A capability above
  `read_sensitive` declares an approval reason and carries a rollback planner,
  and the approval gate refuses it without both.
