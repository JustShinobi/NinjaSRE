---
name: changes
display_name: Change and deploy investigation
description: Asking what changed before this broke, and refusing to blame a coincidence.
domain: changes
applies_when:
  tags: [changes, deploy, vcs, git, configuration]
use_cases:
  - a symptom that started at an identifiable moment
  - a workload that was healthy yesterday and is not today
  - ruling deploys out, so the investigation looks somewhere else
anti_examples:
  - an incident with no start time anybody can name
  - judging whether a change was correct, which is review rather than diagnosis
---

# Identify the resource first, then ask

The single mistake this domain exists to prevent: asking what changed before
knowing what broke.

Asked on the alert text, the question returns whatever a cluster did in the
window — three applies, a merge, and a policy edit — and every one of them is
temporally adjacent to the incident. Asked once the affected resource is
established, the same question returns those same changes *graded*, and the
grading is the whole answer.

## Order of operations

1. **Establish the affected resource.** A workload, a container, a node — the
   thing whose behaviour is wrong, not the thing the alert was named after.
2. **Ask `changes_in_window` for that resource.** The default window reaches
   back a day; narrow it when the symptom has a sharp start.
3. **Read the strength, not the timestamp.** What each one means is below.
4. **Say what you found, including when you found nothing.**

## What each strength means, and what to do with it

| Strength | What it establishes | What to do |
|---|---|---|
| `manages_resource` | The change altered something that governs this resource, through a component that built it | A genuine lead. Name it in the conclusion with its identifier, and say what it touched |
| `touches_shared_policy` | The change altered declarative policy naming this resource or its network | Plausible. Worth confirming against a second observation before it goes in a conclusion |
| `window_only` | The change landed in the same window and nothing connects it | **Not evidence.** Mention it only to say it was ruled out |

A `window_only` change presented as a cause is the failure mode this whole
capability was built to remove. If the conclusion rests on one, the conclusion
is a guess wearing a timestamp.

## Applied is not the same as committed

A change reported as committed and never applied did not touch the cluster. It
can still be worth mentioning — somebody merged something and it is not live —
but it cannot have caused a running system to fail, and a conclusion that blames
one is wrong in a way that is embarrassing to explain.

## The negative is a finding

"No change touched this resource in the last day" belongs in the report. It is
what makes somebody stop looking at deploys and start looking at load, capacity,
or the neighbour that actually broke. Say it with the window and the sources the
answer named; without those it is an assertion.

If the answer says no change source is configured, that is a third thing again:
nothing was consulted, so nothing is ruled out. Report the gap rather than the
negative.

## What this is not for

**Reading what a change contained.** The record carries what was touched and
when, never a diff, and no amount of asking will produce one. Deciding whether a
change was correct is review; this domain answers whether it is a suspect.

**Listing a repository's history.** A window past a few hours is a report about
the repository rather than a question about an incident, and the tool refuses
one past a week.
