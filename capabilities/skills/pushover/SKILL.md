---
name: communication-pushover
display_name: Pushover investigation
description: Pushover as a last-resort notification path: which delivery groups exist, and a finding pushed to a responder's device.
domain: communication
applies_when:
  alert_sources: [pushover]
  tags: [communication, notification, push]
directs_tools:
  - pushover_recent_messages
  - pushover_post_message
requires:
  integrations: [pushover]
---

# Pushover investigation

## Order of operations

1. **Shape before detail.** Call `pushover_recent_messages` over the symptom
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
   `pushover_recent_messages`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## Before writing anything

`pushover_post_message` changes something outside NinjaSRE. It is
gated: a human approves it, and the rollback plan is recorded before it runs.
Reach for it only once the investigation has something worth saying, and never
to ask a question — a read answers questions and a write does not.

## What this is not for

- **A question another system answers in one call.** Reaching for Pushover
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Pushover specifics

- The message title is what a device shows first; the capability's channel argument is used as that title.
- Messages are capped at 1,024 characters, so a long finding is truncated by Pushover rather than rejected.
- The monthly message allowance is per application, so several teams sharing one token share one budget.
