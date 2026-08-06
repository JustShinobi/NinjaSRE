# Service topology and the knowledge base

NinjaSRE keeps two stores about *your* systems rather than about its own past
work: a **topology graph** of what depends on what, and a **knowledge base** of
the runbooks, post-mortems, architecture notes, and procedures your team has
written. An investigation queries both after it has evidence, never before.

This page is for the person who has to answer six questions: how topology gets
populated and stays populated, how documents get in, what happens when the agent
wants to write something down, what either store is allowed to return, how to
switch one off, and what to do when an answer looks wrong.

Episodes — what NinjaSRE learned from its own previous investigations — are
[`episodic-memory.md`](episodic-memory.md), and the playbooks derived from them
are [`strategy-synthesis.md`](strategy-synthesis.md). This page is about the
things you already know and NinjaSRE does not.

## Why neither store is in the opening prompt

Both are queried by the agent, after it holds evidence. The opening prompt
carries two paragraphs of *guidance* — when to ask, what to ask with, and that an
empty answer is an answer — and no content from either store.

That is a deliberate cost. It spends an extra capability call per investigation.
What it buys is the failure it avoids: an alert names one service, the graph
around that service names twenty, and a runbook retrieved on alert text is
retrieved on vocabulary rather than on the failure. An agent handed the wrong
neighbour or the wrong procedure before it has looked at anything reasons from it
all the way to a conclusion, and nothing downstream can detect that.

## Topology

### What is in it

| Thing | What it carries |
|---|---|
| **Service** | An id, a kind (service, database, queue, cache, cluster, external), an environment, an owner, and your annotations |
| **Dependency** | A direction, a kind (`depends_on`, `calls`, `reads_from`, `writes_to`, `deploys_to`), metadata from whichever source saw it, and a verification timestamp |

Direction is always "depends on": an edge runs from the thing that would break to
the thing whose failure would break it. Dependents are the same edges read
backwards, which is why "what could have caused this" and "who is affected" are
one traversal in two directions.

### The three ways to populate it

**Manual entry.** One service or one dependency at a time, for the parts of the
estate no adapter can see. Anything entered this way is marked operator-authored,
which is what stops the next discovery run removing it.

**A file.** Topology as code, applied and re-appliable:

```yaml
version: 1
services:
  - id: checkout
    kind: service
    environment: prod
    owner: team-payments
    annotations:
      note: fronted by the CDN
  - id: payments
    kind: service
  - id: payments-db
    kind: database
dependencies:
  - from: checkout
    to: payments
    kind: calls
  - from: payments
    to: payments-db
    kind: reads_from
    annotations:
      note: read replica only
```

The parser reports **every** problem at once rather than the first, and an edge
naming a service the file does not declare is an error rather than a new node —
in a file that is meant to be the source of truth, `paymnets` is a typo, and
silently creating a service for it would put something in the graph that does not
exist and never gets removed.

**Discovery adapters.** Three ship, and they see genuinely different things:

| Adapter | What it sees | What it cannot see |
|---|---|---|
| Kubernetes | Declared services, the workloads behind them, owner labels, and dependencies declared in a `ninjasre.io/depends-on` annotation | Anything that is not in the cluster, and any dependency nobody declared |
| Service mesh | What actually talks to what, above a request-count floor | Whether the traffic is on a user's critical path |
| Traces | What talks to what *within one request*, above a span-count floor | Anything not instrumented |

Both observational adapters apply a **noise floor** before drawing an edge. Every
mesh reports the occasional stray connection — a health probe on the wrong port,
a scanner, a developer's curl — and an edge drawn from one of those is a
dependency the agent will reason about and nobody has. Unlike a missing edge, a
wrong one is not obviously wrong when you read it.

### Re-running discovery: what changes and what does not

This is the part worth understanding before putting discovery on a schedule.

| Situation | What happens |
|---|---|
| Discovered, not in the graph | Added, stamped with the time it was seen |
| Discovered and in the graph | Verification timestamp refreshed; **annotations kept** |
| In the graph, not discovered, source **healthy** | Removed |
| In the graph, not discovered, source **degraded** | **Marked unverified. Not removed.** |
| Operator-authored | Never removed, whatever the source says |
| Annotated | Annotations always survive |

The fourth row is the one that matters. A Kubernetes API having a bad minute
reports a third of the estate, and a reconciliation that treated the missing two
thirds as retired would delete a team's topology — with the symptom appearing
days later as a blast radius that is quietly wrong. A degraded run marks what it
could not confirm and removes nothing.

Removal is also scoped to what the source says it inspected, so an adapter
watching one namespace never touches another one's dependencies.

Every run produces a diff — added, refreshed, removed, marked unverified,
annotations preserved — which is what you read when somebody asks what happened
to a dependency.

### What a query returns

The agent asks about one service and gets three things at once: what it depends
on, what depends on it, and the blast radius with hop distances. Every service in
the answer carries **when it was last verified**, and anything nobody has
confirmed inside the staleness window is marked in line, where the model reads
it. Operator-authored entries are never marked stale — nobody re-observes a thing
a human wrote down.

Two bounds apply and both are reported:

- **depth** is capped, and a request above the cap is *refused* rather than
  quietly clamped — a blast radius computed at depth 5 when somebody asked for 40
  looks complete and is not;
- **result size** is capped, and an answer that hit the cap says so in a
  sentence: the impact statement is a lower bound.

If the graph is unavailable — no Apache AGE, a database that cannot be reached —
the investigation continues and the degradation is recorded in the trace. It is
never reported as "this service has no dependents", because that is a different
fact and it leads to the opposite decision.

## The knowledge base

### Getting documents in

Documents are uploaded directly or synced from a source you already run:

| Source | Notes |
|---|---|
| **Git** | Markdown in a checked-out repository. Needs no vendor at all, and documentation that lives beside the code is reviewed with the code. Directory `README.md`/`index.md` files become parents; `runbooks/`, `postmortems/`, `architecture/`, `adr/`, and `procedures/` set the document type |
| **Confluence** | Storage-format bodies, ancestors as the tree, labels as tags and type, `webui` links as citations |
| **Notion** | Page blocks flattened to text, headings and lists preserved, code blocks fenced |
| **Google Docs** | Named paragraph styles become headings; tables and embedded objects are skipped rather than flattened into prose |

Each source is a *reader* plus a mapping, so the credentials and the network
calls stay in the integration layer and the mapping is testable without a wiki.
Register a sync on the scheduler and it re-runs; a document whose checksum has
not moved is skipped, so a nightly sync of a hundred runbooks costs the two that
changed.

### What ingestion refuses, and why it refuses rather than redacts

**A document containing a detected secret is rejected.** Not redacted. The
report names the rule, the section, and the line — and never the matched text.

Redaction is right for evidence, which arrives from a system nobody controls and
has to be usable anyway. A knowledge document is *authored*: a credential in one
is a mistake somebody can fix at the source. Storing it redacted would leave a
runbook with a hole in it that nobody knows about, permanently, while the
credential itself stays wherever it was pasted from.

One page being refused never stops a sync. The report names it, and the other
ninety-nine are ingested.

### Chunking, and what a result looks like

A document is cut into overlapping passages that never span a heading, because a
heading is the author's own statement that the subject changed. Cuts fall on
paragraph boundaries first, then sentence boundaries, and only then mid-text.
Consecutive passages overlap, so a sentence that spans a boundary is whole in at
least one of them — a condition in one chunk and its consequence in the next is
how a conditional instruction becomes an unconditional one.

Every result carries its document, its section breadcrumb, and a resolvable
location, and the agent is told to cite rather than paraphrase. A passage
returned without its source is a passage the agent has to restate as its own
finding, and a restated procedure is a procedure nobody wrote.

Search spans the whole of a team's corpus regardless of where a document sits in
the hierarchy. The tree is for humans navigating; an agent that had to know which
folder a runbook was filed in would be an agent that never finds it.

## Agent-proposed knowledge

The agent can propose an addition or an amendment. It **cannot** write one.

A proposal goes into a review queue carrying the investigation that produced it,
so a reviewer can see the evidence without leaving the queue. Nothing reaches the
knowledge base until a human approves it, and the capability's own receipt tells
the agent so — an agent that believed its proposal had taken effect would cite it
later in the same investigation.

Approved documents are attributed: agent-originated, human-approved, by whom and
when. That attribution is shown wherever the document is read, because a reader
who cannot tell an agent's document from an engineer's has no way to weigh it.

Rejections require a reason. Without one the same proposal arrives again after
the next investigation of the same failure, and gets rejected again.

Proposals expire if nobody reviews them. A proposal answered a week after the
incident is answered by somebody who no longer remembers what the cluster looked
like, which is not review.

**Why the review exists at all:** an agent that writes knowledge it later reads,
unreviewed, builds a self-reinforcing belief system. The first investigation's
plausible conclusion becomes a runbook; the second reads the runbook and concludes
the same thing with more confidence; by the fifth there is a well-cited document
describing a cause nobody confirmed. Nothing inside that loop can detect it.

## Turning either store off

Two switches, independent:

```bash
NINJASRE_TOPOLOGY=off      # no graph query, no topology guidance
NINJASRE_KNOWLEDGE=off     # no document search, no knowledge guidance
```

They are separate because "is it worth populating the graph" and "is it worth
writing the runbooks" are two questions, and one switch would answer neither. The
interesting runs are the two middles: a populated graph the agent may not consult,
and a corpus of runbooks it may not search.

Off means the guidance paragraph is not appended *and* the retrieval path is not
reachable — the same code path a deployment that never configured the store takes,
rather than a hook that runs and returns early.

The run trace records the configuration separately from what happened, so
"topology was off" and "topology held nothing for that service" are never
confused for one another.

## When an answer looks wrong

| What you see | Where to look |
|---|---|
| A dependency that no longer exists | The last reconciliation diff. A degraded discovery marks rather than removes, so a stale edge usually means the source has been degraded for a while |
| A dependency that should exist and does not | Whether any adapter can see it. If none can, add it manually or in the import file — it will then be operator-authored and survive discovery |
| An annotation that disappeared | It should not have. Annotations survive every discovery run; report it |
| A blast radius that looks too small | Whether the answer says it was truncated. A partial answer is a lower bound |
| A runbook that was not found | Whether it was ingested at all — a rejected document is named with its reason in the sync report |
| A runbook the agent contradicted | Working as intended. A runbook records what was true when it was written; evidence from this incident wins, and the disagreement should be in the conclusion |
| A search that returned nothing | Whether it *ran*. "Nobody wrote about this" and "there was nowhere to look" are reported differently and mean different things |

---

Both stores live in the operator's own PostgreSQL, alongside everything else.
Topology needs the Apache AGE extension; without it, investigations run degraded
rather than failing. The knowledge base needs `pgvector`, which is also what
episodic memory needs, and it uses the same pluggable embedder — so a deployment
that may not egress keeps full function on the in-process default.
