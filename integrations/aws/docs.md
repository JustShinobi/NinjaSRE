# AWS (CloudWatch Logs)

Log group inventory and event reads from CloudWatch. AWS is the reference
integration for proxy-side signing: SigV4 needs the secret key at the moment a
request is built, so this process never has one and the credential proxy signs
at the network edge.

## Setup

| Field | Where it comes from | Secret |
|---|---|---|
| `access_key_id` | An IAM user's access key, or one an assumed role issued | yes |
| `secret_access_key` | The other half of the pair | yes |
| `session_token` | Only for temporary credentials from STS | yes, optional |
| `region` | The region CloudWatch is read from | no |

```bash
ninjasre integrations setup aws
ninjasre integrations verify aws
```

Prefer temporary credentials. A `session_token` alongside the pair marks the
credential as refreshable, and the proxy renews it before expiry rather than
failing mid-investigation.

The default deployment permits CloudWatch Logs in one region. A deployment
reaching more services or regions builds its injection rule at composition with
`schema.rule_for(services=..., regions=...)`. That list is the egress
allow-list: "AWS" is not a trust boundary, it is a very large surface, and the
integration can reach exactly the regional endpoints somebody declared.

## Permissions

Two IAM actions, and an IAM policy is written per action — so a credential that
reaches CloudWatch at all can still be missing exactly one of them. The symptom
is one capability failing while the other works, which reads as a platform bug
rather than a policy gap.

| Action | What it grants | Without it |
|---|---|---|
| `logs:DescribeLogGroups` | List log groups in the account and region | `aws_list_log_groups` cannot run |
| `logs:FilterLogEvents` | Read events from a log group over a window | `aws_filter_log_events` cannot run |

A minimal policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["logs:DescribeLogGroups", "logs:FilterLogEvents"],
    "Resource": "*"
  }]
}
```

AWS can only report a permission through `iam:SimulatePrincipalPolicy`, which is
a wider grant than this integration needs — asking for it in order to check the
narrow actions would be the wrong trade. So verification probes each action by
performing it on the smallest possible request, and the output says so.

## Limitations

- **CloudWatch Logs has no server-side aggregation.** There is no counting
  endpoint, so "statistics before samples" is approximated by narrowing the log
  group and the window before reading. Logs Insights would answer it and is a
  separate, asynchronous, per-query-charged API; it is not part of this
  integration.
- **One log group per query.** CloudWatch cannot search across groups, so
  finding the right group is a step rather than an optimisation.
- **Retention bounds the window.** A group retaining three days answers a
  question about last week with no results, which is indistinguishable from
  nothing having happened. `aws_list_log_groups` returns each group's retention
  for exactly this reason.
- **Timestamps are epoch milliseconds**, at both ends, and both are required.
  A defaulted window reads whatever CloudWatch considers recent.
- **One rule signs for one service.** SigV4's service name is part of the
  signing scope, so a deployment reaching CloudWatch metrics as well as logs
  builds two clients on two rules — one rule pointed at whichever service it
  happened to get produces signatures AWS rejects with a message that blames the
  key.
- **Everything here is read-only.** Nothing writes a log, deletes a group, or
  changes retention.
