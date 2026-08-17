---
name: vcs-bitbucket
display_name: Bitbucket investigation
description: What landed in a Bitbucket workspace: the repositories that changed recently and the pull requests merged into them.
domain: vcs
applies_when:
  alert_sources: [bitbucket]
  tags: [vcs, git, changes]
directs_tools:
  - bitbucket_change_statistics
  - bitbucket_recent_changes
requires:
  integrations: [bitbucket]
---

# Bitbucket investigation

## Order of operations

1. **Shape before detail.** Call `bitbucket_change_statistics` over the symptom
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
   `bitbucket_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Bitbucket
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Bitbucket specifics

- The query language is Bitbucket's own: `q=name~"checkout"`, with `~` for contains and `AND`/`OR` between clauses.
- `sort=-updated_on` puts the most recently changed repository first, which is the ordering an incident wants.
- Pull requests live under `/2.0/repositories/{workspace}/{repo}/pullrequests`, one call per repository, which is why the listing here is repository-level.
