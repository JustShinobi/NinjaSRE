---
name: cloud_control_plane-aws_cloudtrail
display_name: AWS CloudTrail investigation
description: Who changed what in this AWS account, and when. The change history most incidents turn out to need and most investigations reach for too late.
domain: cloud_control_plane
applies_when:
  alert_sources: [aws_cloudtrail]
  tags: [cloud_control_plane, aws, changes]
directs_tools:
  - aws_cloudtrail_resource_inventory
  - aws_cloudtrail_recent_changes
requires:
  integrations: [aws_cloudtrail]
---

# AWS CloudTrail investigation

## Order of operations

1. **Shape before detail.** Call `aws_cloudtrail_resource_inventory` over the symptom
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
   `aws_cloudtrail_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for AWS CloudTrail
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## AWS CloudTrail specifics

- `ReadOnly=false` is the single most useful filter in an incident: it removes every `Describe` and `List` and leaves the calls that changed something.
- `EventName` is the API operation — `RunInstances`, `UpdateFunctionCode`, `ModifyDBInstance` — and grouping by it answers 'what kind of change happened'.
- `Username` is the IAM identity, and an automated pipeline appears under its role session name rather than under a person.
