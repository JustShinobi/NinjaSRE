---
name: cicd-VENDOR
display_name: VENDOR build investigation
description: Pipeline history. Last green, first failure, and the delta between them.
domain: cicd
applies_when:
  alert_sources: [VENDOR]
  tags: [build, pipeline, ci, release, deploy]
directs_tools:
  - VENDOR_list_pipeline_runs
  - VENDOR_get_run_logs
requires:
  integrations: [VENDOR]
---

# VENDOR build investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Find the last green run.** Not the last run — the last one that passed.
   Everything after it is the search space, and everything before it is not.
2. **Find the first failure.** The one after the last green, not the one that
   alerted. Later failures inherit the first one's cause and describe it worse.
3. **Take the delta between them.** Commits, dependency versions, runner
   image, and pipeline configuration. One of those four changed.
4. **Read the first failure's log, from the bottom.** The final error is the
   symptom; the first non-zero exit is the cause, and they are usually
   different lines.

## What this is not for

- A build that has never passed. There is no delta, and the question is a
  configuration question rather than a regression one.
- Runtime failures of something the pipeline deployed successfully — that is
  the deployed system's problem, not the pipeline's.

## Notes for this vendor

- How long log retention is, which bounds how far back "last green" can be found.
- Whether the runner image is pinned or floating; a floating one makes the
  delta invisible in the commit history.
- Whether re-runs replace the original record or add to it.
