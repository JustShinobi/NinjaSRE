---
name: communication-twilio
display_name: Twilio investigation
description: Twilio as an SMS notification path: the messages this account has sent recently, and a finding delivered to a responder's phone.
domain: communication
applies_when:
  alert_sources: [twilio]
  tags: [communication, notification, sms]
directs_tools:
  - twilio_recent_messages
  - twilio_post_message
requires:
  integrations: [twilio]
---

# Twilio investigation

## Order of operations

1. **Shape before detail.** Call `twilio_recent_messages` over the symptom
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
   `twilio_recent_messages`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## Before writing anything

`twilio_post_message` changes something outside NinjaSRE. It is
gated: a human approves it, and the rollback plan is recorded before it runs.
Reach for it only once the investigation has something worth saying, and never
to ask a question — a read answers questions and a write does not.

## What this is not for

- **A question another system answers in one call.** Reaching for Twilio
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Twilio specifics

- The message-create endpoint takes form encoding in Twilio's documentation and accepts JSON on the same path; JSON is what this client sends.
- `status` is the grouping that answers whether notifications are actually arriving, which is not the same question as whether they were sent.
- `From` must be a number owned by the account; omitting it uses the messaging service default, and an account without one fails at send time.
