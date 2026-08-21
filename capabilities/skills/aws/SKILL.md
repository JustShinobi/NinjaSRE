---
name: logstore-aws
display_name: AWS CloudWatch log investigation
description: CloudWatch logs. Find the group, bound the window, then read.
domain: logstore
applies_when:
  alert_sources: [aws, cloudwatch]
  tags: [logs, lambda, ecs, cloudwatch]
directs_tools:
  - aws_list_log_groups
  - aws_filter_log_events
requires:
  integrations: [aws]
---

# AWS CloudWatch log investigation

CloudWatch cannot count. That single fact reorders everything: with no
server-side aggregation, narrowing has to happen through the log group and the
window before any reading starts, and a query that begins by reading is a query
that pays for every line it discards.

## Order of operations

1. **Find the group.** Call `aws_list_log_groups` with the service name as a
   prefix. Names are conventional rather than guessable — `/aws/lambda/<fn>`,
   `/ecs/<cluster>/<task>` — and a query against a mistyped group costs a turn
   to discover.
2. **Read the retention it returns.** A group retaining three days cannot
   answer a question about last week, and an empty result from one is not
   evidence that nothing happened. Establish this before drawing a conclusion
   from an empty answer.
3. **Bound the window tightly.** Both ends, in epoch milliseconds, around the
   symptom plus enough before it to see normal. CloudWatch charges by scanned
   data and an investigation pays for a wide window in latency.
4. **Filter, do not scan.** Pass a CloudWatch filter pattern — `?ERROR
   ?Exception`, or a JSON selector — so the narrowing happens at AWS rather
   than in the result.
5. **Read the first occurrence, not the loudest.** The earliest matching event
   in the window is where the mechanism started; the hundred after it are the
   same failure repeating.

## Reading the result

`aws_filter_log_events` says when more matched than it returned. Carry that into
the finding — "fifty of an unknown larger number, from the first minute of the
window" is checkable, and "fifty errors" is a claim about volume that was never
measured.

## What this is not for

- **Counting anything.** There is no aggregation here. If the question is "how
  many", a CloudWatch metric answers it in one call and this answers it
  expensively and approximately.
- **Searching across services.** One group per query, by design of the API.
- **Non-logging AWS state.** Instance health, quotas, and recent API activity
  are different services and are not in this integration.

## AWS specifics

- Filter pattern syntax is CloudWatch's own, not a regular expression. Quoted
  terms match literally, `?` is an OR, and JSON logs support `{ $.level = "ERROR" }`.
- Lambda writes one stream per container, so a busy function's events are
  interleaved across many streams. The stream name travels with each event and
  is what separates one container's story from another's.
- Events can appear up to a few seconds after the fact. A window ending
  "now" can miss the most recent events, which matters when the question is
  whether something is still happening.
