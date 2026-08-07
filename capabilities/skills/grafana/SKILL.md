---
name: cloud_control_plane-grafana
display_name: Grafana investigation
description: What Grafana knows about a stack: which dashboards and folders exist, and the annotation timeline of deploys, alert state changes, and anything else a human marked.
domain: cloud_control_plane
applies_when:
  alert_sources: [grafana]
  tags: [cloud_control_plane, dashboards, annotations]
directs_tools:
  - grafana_resource_inventory
  - grafana_recent_changes
requires:
  integrations: [grafana]
---

# Grafana investigation

## Order of operations

1. **Shape before detail.** Call `grafana_resource_inventory` over the symptom
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
   `grafana_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Grafana
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Grafana specifics

- Search takes `query`, `type` (`dash-db` or `dash-folder`), `tag`, and `folderIds`. It is page-numbered from one, not offset-based.
- Annotation times are epoch milliseconds, not seconds. A window given in seconds returns nothing and looks like a quiet period.
- `type=alert` narrows annotations to alert state changes, which is usually the half of the timeline an incident cares about.
