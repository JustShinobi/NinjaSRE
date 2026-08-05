---
name: observability
display_name: Observability investigation
description: Reading logs, metrics, and traces in the order that narrows fastest.
domain: observability
applies_when:
  tags: [logs, metrics, traces, latency, errors, saturation]
use_cases:
  - a latency or error-rate alert with no identified cause
  - deciding which of logs, metrics, or traces will answer the question
anti_examples:
  - a question about billing or account configuration
---

# Reading telemetry without drowning in it

Three signals, three questions, and using the wrong one is how an investigation
spends twenty minutes learning nothing.

- **Metrics** say *that* something changed, and when. They are cheap, complete,
  and almost never explain anything on their own.
- **Logs** say what the system believed was happening. They are expensive and
  incomplete, and they are the only place an error message lives.
- **Traces** say where the time went. When the symptom is latency and a request
  crosses more than two services, this is the signal that answers it, and the
  other two are a detour.

## Statistics before samples

The single most common mistake is reading log lines before counting them.

Four hundred thousand log lines contain a shape: which status codes, which
endpoints, which hosts, and how that distribution differs from an hour ago.
That shape tells you which fifty lines are worth reading. Fifty lines chosen
before you know the shape tell you about fifty lines.

The order is fixed, and each step is one call:

1. **Volume.** How many events in the window at all. This alone distinguishes
   "everything is failing" from "one thing is failing loudly".
2. **Distribution.** Grouped by level, service, status, and host. One dimension
   almost always concentrates the failure.
3. **Trend.** Rising, flat, or falling — and whether it started at the moment
   the symptom did.
4. **Then sample**, from the group the distribution singled out.

Every log integration exposes a statistics call for exactly this reason. It is
the first call, not an optimisation.

## Never look for credentials

Nothing in an investigation reads an API key, a token, or an environment
variable holding one. Authentication happens at the network edge: the tool
carries a handle, and the credential proxy resolves it there.

So a tool failing is never a reason to go looking for configuration. If a
backend is unreachable the tool says so, classified, and the next move is
another signal or another backend — not a search for a secret that is, by
construction, not in this process.

## Narrowing

Each step should divide the search space, and you should be able to say by how
much before making it.

1. **Time.** Bound the window to the symptom, plus enough before it to see
   normal. A window that starts when the alert fired hides the onset.
2. **Dimension.** Group by whatever the platform will group by — status, host,
   endpoint, region, version.
3. **Instance.** Only now read individual records, and read the ones the
   grouping pointed at.

An investigation that reads individual records at step one has skipped both
divisions and is searching linearly.

## The three patterns worth looking for

- **Clustering.** Many errors inside a short window. Points at a single event
  rather than a degradation.
- **Temporal alignment.** The onset matching a deploy, a config change, or a
  traffic shift, to the minute.
- **Propagation.** Service A's errors preceding service B's. The order tells
  you which one to investigate, and it is usually not the one that alerted.

## When the metric looks fine

A flat metric with a real symptom means one of three things, and they are
distinguishable:

- **The aggregation is hiding it.** A p50 that is fine while p99 is not, or a
  fleet average across one bad host. Re-read at a higher percentile, or grouped.
- **The metric is not measuring the failing path.** A success-rate metric that
  counts responses will look healthy while requests time out before responding.
- **The symptom is not where the alert points.** The alert fired on a
  downstream effect, and the cause is a dependency nobody is graphing.

## Correlating across signals

A finding that appears in two signals is worth far more than one that appears
in either. An error-rate rise in metrics, the same rise in log counts, and a
trace showing where the time goes make one mechanism. Any one of them alone
makes a suspect.

When the signals disagree, the disagreement is the finding. Trust the one
closest to the request path and go and find out why the other one is wrong —
that answer is usually the incident.

## Reporting what the telemetry said

A finding that cannot be checked by someone who was not there is a claim. This
is the shape that makes it checkable:

```
Window:       start, end, and the baseline window compared against
Volume:       total events, error count, and the percentage
Affected:     services or endpoints, ranked by count
Onset:        first occurrence, and what else happened at that minute
Pattern:      clustering, temporal alignment, or propagation — which one
Samples:      two or three representative messages, quoted, with context
Hypothesis:   what the shape suggests
Confidence:   high, medium, or low, and what would raise it
```

Quote the messages rather than summarising them. A paraphrased error message
has lost the string that would have matched a previous incident.
