---
name: cloud_control_plane-gcp
display_name: Google Cloud investigation
description: The Google Cloud control plane through Cloud Asset Inventory and Cloud Logging: what exists in a project, and the admin activity that changed it.
domain: cloud_control_plane
applies_when:
  alert_sources: [gcp]
  tags: [cloud_control_plane, gcp, inventory]
directs_tools:
  - gcp_resource_inventory
  - gcp_recent_changes
requires:
  integrations: [gcp]
---

# Google Cloud investigation

## Order of operations

1. **Shape before detail.** Call `gcp_resource_inventory` over the symptom
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
   `gcp_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Google Cloud
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Google Cloud specifics

- `assetTypes` is a filter like `compute.googleapis.com/Instance`, and grouping by `assetType` is what answers 'what kind of thing is in this project'.
- `readTime` reads the inventory as it was at a moment, which is the closest thing here to a change history without turning on asset feeds.
- Project number and project id are both accepted in the path and are not interchangeable in the output.
