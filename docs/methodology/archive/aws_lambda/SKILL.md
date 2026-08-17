---
name: cloud_control_plane-aws_lambda
display_name: AWS Lambda investigation
description: The Lambda control plane: which functions exist, on which runtime and memory setting, and when each was last modified.
domain: cloud_control_plane
applies_when:
  alert_sources: [aws_lambda]
  tags: [cloud_control_plane, aws, serverless]
directs_tools:
  - aws_lambda_resource_inventory
  - aws_lambda_recent_changes
requires:
  integrations: [aws_lambda]
---

# AWS Lambda investigation

## Order of operations

1. **Shape before detail.** Call `aws_lambda_resource_inventory` over the symptom
   window first. It returns a distribution rather than records, so it is
   affordable on a question that matches a great deal, and the group it singles
   out is where the detail should come from.
2. **Compare against normal.** The same call over an equivalent window before
   the symptom. A count is only meaningful against a baseline: "1,200" is a
   number until you know yesterday's was 1,100.
3. **Regroup on whatever concentrated.** If the first grouping was flat, group
   by another field. One dimension almost always concentrates a failure, and
   finding which one is the investigation.
4. **Read where the counts point.** Only now call
   `aws_lambda_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for AWS Lambda
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## AWS Lambda specifics

- Grouping by `Runtime` finds the functions on a runtime that is about to be unsupported; grouping by `MemorySize` finds the ones most likely to be throttled.
- `FunctionArn` carries the region and account, which is what links a function here to an entry in CloudTrail.
- `LastModified` is ISO 8601 with a millisecond fraction, and sorts lexically.
