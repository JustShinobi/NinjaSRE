---
name: investigate
display_name: Investigation methodology
description: The five phases every investigation moves through, and what ends each one.
domain: methodology
applies_when:
  tags: [incident, investigation, alert]
directs_tools:
  - record_hypothesis
  - assess_evidence_sufficiency
  - recall_similar_incidents
use_cases:
  - starting an investigation from an alert with no obvious cause
  - deciding whether enough evidence has been gathered to conclude
---

# The five phases

An investigation is not a search. It is five phases, each with an exit
condition, and the discipline is refusing to move on before the condition is
met — because every phase skipped is re-entered later, with less time.

Budget roughly six to eight tool calls per phase. Needing more usually means
the phase before this one was left unfinished.

## 1. Establish the symptom

Say precisely what is wrong, for whom, since when, and how you know. "Checkout
is slow" is not a symptom; "p99 latency on `POST /checkout` rose from 180ms to
4.2s at 14:12 UTC, affecting all regions" is.

Four things make a symptom usable:

- **Symptom** — errors, latency, or unavailability, with numbers.
- **Timeline** — when it started, and whether it is ongoing.
- **Impact** — users affected, objective breached, revenue at risk.
- **Suspects** — which systems are plausibly involved.

**Exit condition:** the symptom is quantified and time-bounded.

## 2. Establish the blast radius

Find the edges. One region or all of them, one endpoint or every endpoint, one
customer or the whole tenant. The shape of the boundary usually names the layer:
a single availability zone points at infrastructure, a single endpoint points at
code, a single customer points at data.

**Exit condition:** you can say what is *not* affected, not only what is.

## 3. Recall, once there is something to recall against

`recall_similar_incidents` belongs *here*, not at the start. Searched on the raw
alert text it returns whatever shares vocabulary with the alert; searched on a
symptom, a component, and a boundary it returns incidents that were actually
like this one.

Prioritise resolved matches whose root cause matches the shape of what you have
found so far. A previous investigation that found the answer is evidence, and
repeating its work is the most expensive way to rediscover it.

**Exit condition:** either a prior incident worth reading, or a definite no.

## 4. Establish what changed, then the mechanism

Almost everything that breaks was working recently, so something changed.
Deploys, configuration, feature flags, traffic, upstream dependencies, and
certificate expiry are the usual six. Check them against the time the symptom
started, not against the time the alert fired — those differ, often by a lot.

Correlation names a suspect. The mechanism is the story of how that change
produces this symptom, and it must be checkable. "The deploy caused it" is a
suspect. "The deploy raised the connection pool timeout above the load
balancer's idle timeout, so pooled connections are being closed underneath
in-flight requests" is a mechanism, and it predicts something you can go and
look at.

Rank the alternatives rather than committing to the first. Use
`record_hypothesis` for each, with the observation that would kill it:

- **H1** — the most likely, given the evidence so far.
- **H2** — the next most likely.
- **H3** — the explanation that would embarrass you if it turned out to be right.

A hypothesis with no disconfirming observation is a belief. Gather the
observation that separates H1 from H2 before gathering anything else — that is
the call that halves the search space, and every other call does not.

**Exit condition:** one hypothesis survives an observation that could have
killed it.

## 5. Conclude, or say what is missing

Call `assess_evidence_sufficiency` before writing a conclusion. If the
supporting evidence does not exist, what you have is the best current
hypothesis, and it must be reported as one.

Structure the conclusion so a reader can check it:

```
Root cause:   the specific, actionable cause
Evidence:     the observations that support it — each with a timestamp,
              a value, or a message, not a summary
Timeline:     what happened, in order
Confidence:   high, medium, or low, and why
Actions:      immediate mitigation, then the durable fix, then prevention
Caveats:      what could not be determined, and what would settle it
```

Naming the missing evidence is a useful result. "The traces would settle this
and tracing is not configured for this service" is something an operator can
act on. A confident conclusion resting on three metric readings is not.

**Exit condition:** a conclusion with its evidence, or a hypothesis with the
observation that would resolve it.

## Intellectual honesty

The investigation is only worth what its weakest claim is worth.

- **Distinguish observed from inferred.** A fact has a timestamp and a value. An
  inference has a reason. Never let the second wear the clothes of the first.
- **State confidence, and what would change it.** "High, unless the deploy
  timestamps are wrong" is a useful sentence.
- **Say when you do not know.** An investigation that ends in "the evidence does
  not distinguish these two causes, and here is the query that would" is a
  success. One that picks a cause to avoid saying so is not.

## Efficiency

- **Do not repeat a query with the same parameters.** The result is already in
  the trace, and re-running it spends an iteration to learn nothing.
- **Start narrow and widen.** A query over everything returns something for
  every investigation, which is why it distinguishes none of them.
- **Prefer the observation that divides the search space.** Before making a
  call, say what each possible answer would rule out. If neither answer rules
  anything out, it is not worth the call.

## What ends an investigation badly

- **Restarting to see if it helps.** It destroys the process state that would
  have explained the failure, and the symptom usually returns.
- **Sampling before counting.** Fifty log lines out of four hundred thousand
  describe the fifty, and the shape of the whole is what tells you where to
  look.
- **Following the first correlation.** Deploys happen constantly; one landing
  near the symptom is weak evidence until the mechanism connects them.
- **Concluding from a single kind of evidence.** Metrics say something changed,
  logs say what the system thought was happening, traces say where the time
  went. A conclusion drawn from one of the three is a conclusion about one
  third of the system.
