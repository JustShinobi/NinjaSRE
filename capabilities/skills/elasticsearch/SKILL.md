---
name: logstore-elasticsearch
display_name: Elasticsearch investigation
description: Search over Elasticsearch indices, counted by field before any document is read, for the deployments whose logs live there rather than in a hosted log product.
domain: logstore
applies_when:
  alert_sources: [elasticsearch]
  tags: [logstore, logs, search]
directs_tools:
  - elasticsearch_log_statistics
  - elasticsearch_sample_logs
requires:
  integrations: [elasticsearch]
---

# Elasticsearch investigation

## Order of operations

1. **Shape before detail.** Call `elasticsearch_log_statistics` over the symptom
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
   `elasticsearch_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Elasticsearch
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Elasticsearch specifics

- `query_string` syntax is Lucene: `service:checkout AND log.level:error`, with `-` for negation and quotes for phrases.
- The index pattern goes in the path — `/logs-*/_search` — and searching `/_search` hits every index the key can see, which is usually more than intended.
- Sorting by `@timestamp` descending is what makes a sample the newest documents rather than an arbitrary set.
