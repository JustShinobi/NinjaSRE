---
name: cloud_control_plane-aws_ec2
display_name: AWS EC2 investigation
description: EC2 instance state for a region: how many instances are in which state, and the instances themselves with their type, zone, and launch time.
domain: cloud_control_plane
applies_when:
  alert_sources: [aws_ec2]
  tags: [cloud_control_plane, aws, compute]
directs_tools:
  - aws_ec2_resource_inventory
  - aws_ec2_recent_changes
requires:
  integrations: [aws_ec2]
---

# AWS EC2 investigation

## Order of operations

1. **Shape before detail.** Call `aws_ec2_resource_inventory` over the symptom
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
   `aws_ec2_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for AWS EC2
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## AWS EC2 specifics

- Every call is `GET /?Action=<Operation>&Version=2016-11-15`, which is the query protocol rather than REST.
- `IncludeAllInstances=true` is what makes stopped instances appear; without it the answer covers running ones only and a stopped fleet reads as an empty region.
- Instance state is at `instanceState.name` — `running`, `stopped`, `terminated` — and is the grouping that answers 'is anything down'.
