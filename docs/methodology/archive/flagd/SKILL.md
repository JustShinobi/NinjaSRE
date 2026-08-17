---
name: cloud_control_plane-flagd
display_name: flagd investigation
description: OpenFeature's flagd: which feature flags this deployment is serving and in what state, which is the change history nothing else records.
domain: cloud_control_plane
applies_when:
  alert_sources: [flagd]
  tags: [cloud_control_plane, flags, openfeature]
directs_tools:
  - flagd_resource_inventory
  - flagd_recent_changes
requires:
  integrations: [flagd]
---

# flagd investigation

## Order of operations

1. **Shape before detail.** Call `flagd_resource_inventory` over the symptom
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
   `flagd_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for flagd
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## flagd specifics

- `ResolveAll` returns every flag with its value, variant, and reason in one call, which is what makes a flag inventory cheap.
- `reason` is `STATIC`, `TARGETING_MATCH`, `DEFAULT`, or `ERROR`; an `ERROR` reason means the flag definition is wrong rather than that the flag is off.
- Resolution depends on the evaluation context, so the same flag can be on for one user and off for another — an inventory is not a statement about any one user.
