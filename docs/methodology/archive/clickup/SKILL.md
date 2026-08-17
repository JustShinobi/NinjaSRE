---
name: ticketing-clickup
display_name: ClickUp investigation
description: What ClickUp already tracks: the tasks in a list, in what status, and which are worth reading before another is created.
domain: ticketing
applies_when:
  alert_sources: [clickup]
  tags: [ticketing, tasks, issues]
directs_tools:
  - clickup_issue_statistics
  - clickup_recent_issues
requires:
  integrations: [clickup]
---

# ClickUp investigation

## Order of operations

1. **Shape before detail.** Call `clickup_issue_statistics` over the symptom
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
   `clickup_recent_issues`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for ClickUp
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## ClickUp specifics

- `status.status` is the status name and `status.type` is the category — `open`, `custom`, `done`, `closed` — and the category is the portable grouping.
- `date_updated` is epoch milliseconds as a string, which sorts wrongly as text.
- `subtasks=true` is what stops a nested task being invisible, and it is off by default.
