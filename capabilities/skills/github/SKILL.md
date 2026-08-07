---
name: vcs-github
display_name: GitHub investigation
description: What landed in a repository and when: the commits on its default branch and the pull requests recently merged into it.
domain: vcs
applies_when:
  alert_sources: [github]
  tags: [vcs, git, changes]
directs_tools:
  - github_change_statistics
  - github_recent_changes
requires:
  integrations: [github]
---

# GitHub investigation

## Order of operations

1. **Shape before detail.** Call `github_change_statistics` over the symptom
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
   `github_recent_changes`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for GitHub
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## GitHub specifics

- Search qualifiers do the narrowing: `repo:acme/checkout`, `author-date:>2026-08-07`, `is:pr is:merged`, `base:main`.
- Grouping commits by `commit.author.name` answers 'was this one person's change or a release'; grouping by `author.login` uses the account rather than the committer's configured name.
- Pull requests come back through the issues search endpoint, which is why the second capability queries `is:pr` rather than a pull-requests path.
