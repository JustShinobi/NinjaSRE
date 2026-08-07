---
name: ticketing-confluence
display_name: Confluence investigation
description: What has already been written down: the Confluence pages matching a search, and the ones most recently changed.
domain: ticketing
applies_when:
  alert_sources: [confluence]
  tags: [ticketing, docs, runbooks]
directs_tools:
  - confluence_issue_statistics
  - confluence_recent_issues
requires:
  integrations: [confluence]
---

# Confluence investigation

## Order of operations

1. **Shape before detail.** Call `confluence_issue_statistics` over the symptom
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
   `confluence_recent_issues`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Confluence
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Confluence specifics

- CQL: `space = OPS AND type = page AND text ~ "cart limit" ORDER BY lastmodified DESC`.
- `expand=version` is what brings back who changed a page and when; without it the result says nothing about freshness.
- Body content is not returned by search and needs a per-page call, which is why these capabilities return metadata rather than prose.
