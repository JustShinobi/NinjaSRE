---
name: cloud_control_plane-aws_elb
display_name: AWS ELB investigation
description: Elastic Load Balancing state: which load balancers exist and in what state, and the target groups behind them.
domain: cloud_control_plane
applies_when:
  alert_sources: [aws_elb]
  tags: [cloud_control_plane, aws, network]
directs_tools:
  - aws_elb_resource_inventory
  - aws_elb_recent_changes
requires:
  integrations: [aws_elb]
---

# AWS ELB investigation

## Order of operations

1. **Shape before detail.** Call `aws_elb_resource_inventory` over the symptom
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
   `aws_elb_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for AWS ELB
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## AWS ELB specifics

- `State.Code` is `active`, `provisioning`, or `failed`, and grouping by it is the one-call answer to 'is the load balancing layer healthy'.
- A load balancer ARN carries the region and account and is what a CloudWatch dimension refers to.
- `Scheme` distinguishes `internet-facing` from `internal`, which is usually the first thing worth knowing about a load balancer named in an alert.
