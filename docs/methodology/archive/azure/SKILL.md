---
name: cloud_control_plane-azure
display_name: Azure investigation
description: The Azure Resource Manager control plane: what exists in a subscription, and the activity log entries that changed it.
domain: cloud_control_plane
applies_when:
  alert_sources: [azure]
  tags: [cloud_control_plane, azure, inventory]
directs_tools:
  - azure_resource_inventory
  - azure_recent_changes
requires:
  integrations: [azure]
---

# Azure investigation

## Order of operations

1. **Shape before detail.** Call `azure_resource_inventory` over the symptom
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
   `azure_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Azure
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Azure specifics

- `$filter=resourceType eq 'Microsoft.Compute/virtualMachines'` narrows the inventory; grouping by `type` answers what kinds of thing exist.
- The activity log's `$filter` takes `eventTimestamp ge '<ISO>'` and refuses a window wider than 90 days outright.
- `nextLink` is a whole URL rather than a token, and the base client follows an absolute path while the proxy's allow-list still applies.
