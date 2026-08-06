# Episodic memory

NinjaSRE remembers every investigation it finishes. This page is for the person
who has to answer four questions about that: what is stored, what the `resolved`
flag actually claims, how to turn memory off, and how to get rid of it.

## What an episode is

One episode is one investigation *conversation* — not one turn, not one alert.
It is keyed by the conversation's correlation id, so a follow-up turn updates the
episode rather than writing a second one, and a sub-agent's work belongs to its
parent's episode.

Each episode records:

| Field | What it holds |
|---|---|
| `issue_type` | A short label for the class of failure — `oom_kill`, `certificate_expiry` |
| `issue_description` | One sentence saying what was wrong, with the numbers |
| `severity` | `critical`, `high`, `medium`, `low`, or `unknown` |
| `components` | The systems the failure was about, each as `{type, name}` |
| `capabilities_used` | Which capabilities the investigation called, in order |
| `key_findings` | What each capability revealed, naming the capability and the query |
| `resolved` | Whether a root cause was established — see below |
| `root_cause` | The cause the evidence supported, if any |
| `summary` | A few sentences a future investigation would want to read |
| `effectiveness_score` | How well the run went, as a documented formula |
| `duration_seconds`, `iterations` | What it cost |
| `org_id`, `team_node_id` | Who it belongs to |

Plus an embedding, and the model and width that produced it.

**Investigations that failed are kept.** An unresolved episode is the raw
material for knowing what does not work, and a corpus of successes only measures
how well the system does on incidents it already handles.

**Very short results are not.** An investigation whose answer is under 200
characters produces no episode, and the skip is recorded. A corpus full of
"nothing conclusive" dilutes every search run against it.

## What `resolved` means

**`resolved` means the investigation established a root cause and had evidence
behind it. It does not mean production was fixed.**

That distinction is not pedantry. An investigation that correctly concluded "a
bad deploy lowered the memory limit" is resolved whether or not anyone has rolled
it back — NinjaSRE has no way to know whether they did, and a flag that claimed
otherwise would be a claim nothing in the process can check. An investigation
that guessed right without evidence is *not* resolved.

Ranking promotes resolved episodes, so getting this wrong would mean promoting
episodes on the strength of somebody having restarted a pod.

## Guardrails and tenancy

Episode content passes the guardrail engine before it is written. A matched
secret is redacted and the rules that fired are recorded on the episode — the
record is kept, because the investigation happened and the secret is already out
of the text.

Episodes are scoped by organisation and team. Cross-organisation retrieval is
structurally impossible (no repository port takes an organisation), and the team
boundary is enforced twice: as a filter inside the vector index and as a check on
every row that comes back.

## How recall works

Memory is **not** injected into the opening prompt. The agent is told memory
exists and told to search it only once it holds concrete evidence — an error
string, an exit code, a failing component. Searching on a raw alert returns
episodes that share vocabulary rather than a cause, and an agent handed one of
those before it has looked at anything reasons from it all the way to a wrong
conclusion.

Results are ranked by a documented weighted sum of five terms: similarity,
whether a root cause was established, component overlap, effectiveness, and
recency. There is no model call anywhere in the retrieval path, so the same query
returns the same order every time.

Every recall is recorded in the run trace: the query, the filters, what came
back, and whether the answer went on to use any of it.

## Embeddings

The default embedder runs in-process and reaches no network, so a deployment that
may not egress keeps full memory function. It is a lexical model: it will match
"OOMKilled on payments-api" to a previous OOMKill on payments-api, and it will
not match "the pod ran out of memory" to it.

To use a stronger model, provide an embedder to `MemoryService` and re-embed. The
index records which model wrote every vector, so re-declaring it with a different
model fails at startup rather than silently halving recall quality. Re-embedding
opens a new generation, fills it while search keeps reading the old one, verifies
the count, and swaps atomically — search stays up throughout, and a generation
that came up short is never activated.

## Turning memory off

Reading and writing switch independently.

```bash
NINJASRE_MEMORY_READ=off     # the agent may not consult the corpus
NINJASRE_MEMORY_WRITE=off    # nothing new is written
```

Anything other than `0`, `false`, `no`, or `off` reads as on, including a typo —
a mis-spelled value must not silently disable memory.

A disabled switch means the corresponding hook is **not installed**, not that it
is installed and does nothing. "Memory off" is the same code path a deployment
without memory takes, which is what makes it a usable baseline: an ablation run
compares against a run that is otherwise identical, not against one carrying two
extra hooks in its dispatch order.

The interesting experiment is `NINJASRE_MEMORY_READ=off` with writing left on: a
populated corpus the agent is not allowed to consult isolates recall's
contribution while leaving the corpus intact for the run after.

## Purging and retention

Episodes and their vectors are deleted together, in one transaction. Deleting one
without the other leaves either a neighbour that resolves to nothing or a row
nothing can find.

```python
from platform.memory import purge_episodes, purge_expired

await purge_episodes(gateway, scope, ["conv-1", "conv-2"])   # named episodes
await purge_expired(gateway, scope)                          # past the retention window
```

The retention window defaults to 730 days — far longer than run traces, on
purpose. The trace is the evidence for one investigation; the episode corpus is
what every ablation measures learning against, and deleting it deletes the
ability to prove the system improved.

## Proving it helps

Two numbers, both in the test suite rather than in a claim:

- A synthetic scenario is run against an empty corpus, then run again against the
  corpus the first run left behind, and the iteration count of each is recorded.
  The reduction is the feature's proof of value.
- The same repeat, with recall switched off, has to take the first run's
  trajectory. If it did not, the reduction would be measuring something other
  than memory.
