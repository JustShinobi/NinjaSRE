---
name: cloud_control_plane-aws_rds
display_name: AWS RDS investigation
description: The RDS control plane: which database instances exist and in what state, and the events RDS recorded against them — failovers, restarts, parameter changes.
domain: cloud_control_plane
applies_when:
  alert_sources: [aws_rds]
  tags: [cloud_control_plane, aws, database]
directs_tools:
  - aws_rds_resource_inventory
  - aws_rds_recent_changes
requires:
  integrations: [aws_rds]
---

# AWS RDS investigation

## Order of operations

1. **Shape before detail.** Call `aws_rds_resource_inventory` over the symptom
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
   `aws_rds_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for AWS RDS
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## AWS RDS specifics

- `Duration` is minutes and defaults to 60, which is usually narrower than an incident window — 1440 is a day.
- `DBInstanceStatus` is the grouping that answers 'is anything not available': `available`, `modifying`, `failed`, `storage-full`.
- A failover appears as an event with `Message` naming the availability zone, and it is the single most useful record RDS produces during an incident.
