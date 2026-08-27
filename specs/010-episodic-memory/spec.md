# Feature 010 — Episodic Memory

- **Wave:** 2 — Memory & Knowledge
- **Branch:** `feat/010-episodic-memory`
- **Status:** Draft
- **Depends on:** 002, 003, 004, 005, 006
- **Blocks:** 011, 012, 028

## Summary

The system remembers every investigation as an episode — what broke, which
components, which capabilities helped, what the root cause turned out to be, and
how effective the run was. Recall is **agent-driven**: memory is retrieved after
concrete evidence exists, never pre-injected on a vague alert. Every mechanism
ships with an ablation switch, because Constitution Article VII forbids claiming
learning that has not been measured.

## User scenarios

### Primary story

A payments pod is CrashLoopBackOff at 03:00. The agent gathers evidence, sees exit
code 137, and only then searches memory. It surfaces a resolved episode from six
weeks ago with the same signature on the same service, including which capability
sequence found it and what the cause was. The investigation converges in three
iterations instead of eleven.

### Acceptance scenarios

1. **Given** an investigation completes with a substantive result, **when** the
   `on_run_end` hook fires, **then** exactly one episode is written for that
   conversation, keyed by correlation id.
2. **Given** a second turn in the same conversation, **when** it completes, **then**
   the existing episode is updated, not duplicated.
3. **Given** an investigation with a result shorter than the minimum length,
   **when** it completes, **then** no episode is written and the skip is recorded.
4. **Given** an agent with no concrete evidence yet, **when** it considers memory,
   **then** guidance instructs it to gather facts first — memory is not
   pre-injected into the initial prompt.
5. **Given** concrete evidence (error text, failing component), **when** the agent
   invokes the memory capability, **then** semantically similar past episodes
   return, ranked, scoped to the team.
6. **Given** returned episodes, **when** they are ranked, **then** resolved
   episodes with matching components and higher effectiveness rank above
   unresolved ones.
7. **Given** an episode, **when** it is written, **then** it records issue type,
   description, severity, components, capabilities used, key findings, resolved
   flag, root cause, summary, effectiveness score, and duration.
8. **Given** the ablation switch set to disabled, **when** investigations run,
   **then** no memory is written or retrieved, and the run is otherwise identical.
9. **Given** a team boundary, **when** memory is searched, **then** only that
   team's episodes are visible — never another team's or another org's.
10. **Given** an embedding model change, **when** re-embedding runs, **then**
    search remains available throughout and switches atomically to the new
    generation.

### Edge cases

- An investigation that ends in failure — still worth remembering as an
  anti-pattern source.
- An episode whose components could not be extracted.
- Two concurrent turns in the same conversation racing to write the episode.
- A very long investigation producing an oversized summary.
- Episode extraction itself failing — must never fail the investigation.
- Memory search returning nothing relevant, which is the common case early on.

## Requirements

### Functional

**Episode model and writing**

- **FR-001** An episode MUST correspond to exactly one conversation, keyed by
  correlation id. Repeat turns update it.
- **FR-002** An episode MUST record: `issue_type`, `issue_description`, `severity`,
  `components`, `capabilities_used`, `key_findings`, `resolved`, `root_cause`,
  `summary`, `effectiveness_score`, `duration_seconds`, `org_id`, `team_node_id`,
  timestamps, and an embedding.
- **FR-003** `resolved` MUST mean *a root cause was established with supporting
  evidence*. It MUST NOT mean production was fixed. This meaning MUST be
  documented wherever the flag surfaces.
- **FR-004** A `Component` MUST be a typed subject — `{type, name}` — where type is
  free-form (`service`, `deployment`, `database`, `job`, …).
- **FR-005** Episode extraction MUST run post-turn from the prompt, result, and
  tool trace, and MUST NOT fail the investigation on error.
- **FR-006** Results below `MIN_EPISODE_RESULT_LENGTH` MUST be skipped, with the
  skip recorded.
- **FR-007** `effectiveness_score` MUST be computed from resolution status, root
  cause presence, evidence backing, and trajectory efficiency, and MUST be
  documented as a formula rather than a heuristic in prose.
- **FR-008** Concurrent writes for the same correlation id MUST be safe —
  last-writer-wins on an upsert, never a duplicate.

**Recall**

- **FR-009** Memory MUST NOT be pre-injected into the initial investigation prompt.
- **FR-010** Root-agent guidance MUST instruct the agent to search memory only
  after concrete evidence exists, with a specific query.
- **FR-011** A `memory-search` capability MUST exist, taking a natural-language
  query plus optional component and issue-type filters.
- **FR-012** Retrieval MUST use vector similarity over the episode embedding,
  scoped to the requesting team.
- **FR-013** Ranking MUST combine similarity, resolution status, component
  overlap, effectiveness score, and recency, with documented weights.
- **FR-014** Results MUST include the capability sequence used, so the agent can
  reuse a known-good trajectory.
- **FR-015** Retrieval MUST return an empty result cleanly; no relevant memory is
  a normal outcome, not an error.

**Embeddings**

- **FR-016** Embeddings MUST be computed from issue type, description, summary,
  and root cause.
- **FR-017** The embedding provider MUST be pluggable and MUST support a local
  model so a no-egress deployment retains memory.
- **FR-018** Each embedding MUST record its model and dimension; a mismatch MUST
  fail loudly at write.
- **FR-019** Re-embedding MUST run as a background generation swap with search
  available throughout.

**Ablation and measurement**

- **FR-020** A team-scoped switch MUST disable memory read, memory write, or both.
- **FR-021** With memory disabled, an investigation MUST be otherwise identical, so
  the evaluation suite isolates memory's contribution.
- **FR-022** Every recall MUST be recorded in the run trace: query, results
  returned, and whether the agent acted on them.

**Isolation**

- **FR-023** Episodes MUST be scoped by org and team; cross-team retrieval MUST be
  impossible.
- **FR-024** Episode content MUST pass the guardrail engine before persistence.

### Key entities

| Entity | Description |
|---|---|
| **Episode** | One investigation conversation, with outcome and embedding |
| **Component** | A typed affected subject `{type, name}` |
| **KeyFinding** | `{capability, query, finding}` — what a capability revealed |
| **ScoredEpisode** | A retrieval result with its ranking components exposed |
| **EffectivenessScore** | The documented formula output in [0, 1] |
| **EmbeddingGeneration** | Model, dimension, and generation identifier |
| **MemoryPolicy** | Per-team read/write enablement for ablation |

## Success criteria

- **SC-001** Exactly one episode per conversation, verified under concurrent turns.
- **SC-002** No episode content appears in the initial investigation prompt —
  asserted by inspecting the prompt (FR-009).
- **SC-003** On a synthetic scenario replayed a second time, memory recall reduces
  iteration count measurably versus the first run — this is the feature's proof of
  value.
- **SC-004** With memory disabled, scenario scores match the pre-memory baseline
  within noise, proving FR-021.
- **SC-005** Cross-team retrieval is impossible — asserted per port and per
  capability.
- **SC-006** Extraction failure never fails an investigation — verified by forcing
  it.
- **SC-007** A no-egress deployment with a local embedding model retains full
  memory function.
- **SC-008** Re-embedding 100k episodes keeps search available throughout.

## Out of scope

- Strategy synthesis from multiple episodes (feature 011)
- Service topology (feature 012)
- Operator-authored knowledge (feature 012)
- Memory browsing UI (feature 021)

## Clarifications

| Question | Resolution |
|---|---|
| Why not pre-inject relevant memory into the prompt? | Swapnil's upstream reasoning, adopted deliberately: on a vague alert, similarity search returns superficially-similar-but-irrelevant episodes that anchor the agent on the wrong hypothesis. Retrieval after evidence exists is both cheaper and more accurate. |
| Should failed investigations be remembered? | Yes. Unresolved and low-effectiveness episodes are the raw material for anti-patterns in feature 011 — knowing what did not work is half the value. |
| Is `resolved` a claim that production was fixed? | Explicitly not (FR-003). Conflating them would make the metric meaningless and the UI misleading. |
| How is memory's value proven rather than asserted? | SC-003 and SC-004 plus the ablation harness in feature 028. If memory does not improve scores, the number says so. |
