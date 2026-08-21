---
name: ticketing-google_docs
display_name: Google Docs investigation
description: What the team has written in Google Docs: the documents matching a search, and the ones most recently modified.
domain: ticketing
applies_when:
  alert_sources: [google_docs]
  tags: [ticketing, docs, runbooks]
directs_tools:
  - google_docs_issue_statistics
  - google_docs_recent_issues
requires:
  integrations: [google_docs]
---

# Google Docs investigation

## Order of operations

1. **Shape before detail.** Call `google_docs_issue_statistics` over the symptom
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
   `google_docs_recent_issues`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Google Docs
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Google Docs specifics

- Drive's query language: `name contains 'runbook' and mimeType = 'application/vnd.google-apps.document' and trashed = false`.
- `modifiedTime` is what says whether a document is current, and it belongs in any finding that cites one.
- Document *content* is the Docs API rather than Drive, and is a second call per document — these capabilities deliberately return metadata.
