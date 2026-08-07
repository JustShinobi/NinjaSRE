---
name: logstore-azure_monitor
display_name: Azure Monitor investigation
description: KQL against a Log Analytics workspace: the shape of what a query matched, and the records behind it, for the estates whose telemetry lands in Azure.
domain: logstore
applies_when:
  alert_sources: [azure_monitor]
  tags: [logstore, logs, kql]
directs_tools:
  - azure_monitor_log_statistics
  - azure_monitor_sample_logs
requires:
  integrations: [azure_monitor]
---

# Azure Monitor investigation

## Order of operations

1. **Shape before detail.** Call `azure_monitor_log_statistics` over the symptom
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
   `azure_monitor_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Azure Monitor
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Azure Monitor specifics

- KQL: `AppTraces | where SeverityLevel >= 3 | summarize count() by AppRoleName`. `summarize` is what makes the counting happen server-side.
- `timespan` is ISO 8601 interval — `2026-08-07T11:00:00Z/2026-08-07T12:00:00Z` — and overrides any time filter inside the query.
- Table names differ between the classic Application Insights schema and the workspace-based one, which is the most common cause of an empty answer.
