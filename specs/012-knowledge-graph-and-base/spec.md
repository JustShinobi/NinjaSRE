# Feature 012 — Knowledge Graph and Knowledge Base

- **Wave:** 2 — Memory & Knowledge
- **Branch:** `feat/012-knowledge-graph-and-base`
- **Status:** Draft
- **Depends on:** 003, 006, 010
- **Blocks:** 017, 021, 028

## Summary

Two complementary knowledge stores. The **topology graph** holds service
dependencies so the agent knows blast radius before it starts guessing. The
**knowledge base** holds operator-authored runbooks and documentation, chunked and
searchable, with a review workflow for agent-proposed additions. Both are queried
agent-driven after evidence exists, never pre-injected.

## User scenarios

### Primary story

An alert fires on `checkout`. Once the agent knows the affected service, it queries
topology: `checkout` depends on `payments`, `inventory`, and a Postgres instance;
four services depend on `checkout`. The agent focuses evidence-gathering on the
three upstreams and correctly scopes the impact statement to the four downstreams —
without guessing from naming conventions.

### Acceptance scenarios

1. **Given** a known service, **when** topology is queried, **then** direct
   dependencies, direct dependents, and blast radius to depth N return within the
   configured bounds.
2. **Given** an unknown service, **when** topology is queried, **then** an empty
   result returns cleanly and the investigation continues.
3. **Given** the graph is unavailable, **when** topology is queried, **then** the
   investigation continues without topology context and the degradation is
   recorded.
4. **Given** an operator uploads a runbook, **when** ingestion runs, **then** it is
   chunked, embedded, and searchable, scoped to the team.
5. **Given** an agent with concrete evidence, **when** it searches the knowledge
   base, **then** relevant runbook sections return with their source document and
   location.
6. **Given** the agent discovers something worth recording, **when** it proposes a
   knowledge change, **then** the proposal enters a review queue and is **not**
   applied until a human approves.
7. **Given** topology is populated from a discovery source, **when** discovery
   runs again, **then** nodes and edges are reconciled — stale edges removed,
   new ones added — without losing operator-authored annotations.
8. **Given** the ablation switch disables topology or the knowledge base, **when**
   investigations run, **then** the corresponding source is unavailable and the
   run is otherwise identical.
9. **Given** a team boundary, **when** either store is queried, **then** only that
   team's data is visible.

### Edge cases

- A topology cycle (`A → B → A`), which is legal in real systems.
- Blast radius on a hub service with thousands of dependents.
- A runbook document larger than the chunking budget.
- Conflicting information between a runbook and an episode.
- An agent-proposed change that contradicts an existing approved document.
- Topology discovery that partially fails, leaving inconsistent edges.
- A knowledge document containing credentials or PII.

## Requirements

### Functional

**Topology graph**

- **FR-001** The graph MUST store service nodes with type, name, environment,
  owner, and operator annotations.
- **FR-002** Edges MUST carry a dependency kind (`calls`, `reads_from`,
  `writes_to`, `deploys_to`, `depends_on`) and optional metadata.
- **FR-003** Queries MUST be limited to the fixed parameterised catalogue defined
  in feature 006. LLM-generated graph queries MUST NOT be executed.
- **FR-004** Traversal MUST be bounded by `MAX_GRAPH_DEPTH` and
  `MAX_GRAPH_RESULTS`; truncation MUST be reported in the result.
- **FR-005** Cycles MUST be handled without infinite traversal.
- **FR-006** Topology MUST be populatable from: manual entry, file import
  (declarative topology as code), and discovery adapters (Kubernetes services,
  service-mesh telemetry, trace-derived dependencies).
- **FR-007** Re-discovery MUST reconcile rather than replace: stale edges removed,
  new edges added, operator annotations preserved.
- **FR-008** A partially-failed discovery MUST NOT delete edges it could not
  verify; it MUST mark them unverified with a timestamp.
- **FR-009** Graph unavailability MUST degrade the investigation gracefully with
  the degradation recorded (FR acceptance 3).

**Knowledge base**

- **FR-010** Documents MUST support: runbooks, postmortems, architecture notes,
  and operational procedures.
- **FR-011** Ingestion MUST chunk documents with overlap, embed chunks, and
  preserve source document identity and location for citation.
- **FR-012** Documents MUST be organisable in a hierarchy (tree), with search
  spanning the whole tree scoped to the team.
- **FR-013** Search MUST return chunks with their source document, section, and a
  link, so the agent can cite rather than paraphrase.
- **FR-014** Ingestion MUST support: direct upload, and sync from Confluence,
  Notion, Google Docs, and Git repositories (using feature 025's integrations).
- **FR-015** Document content MUST pass the guardrail engine on ingestion; a
  document containing detected secrets MUST be rejected with the location
  reported.

**Agent-proposed knowledge**

- **FR-016** The agent MUST be able to propose a knowledge addition or amendment.
- **FR-017** A proposal MUST enter a review queue and MUST NOT take effect until a
  human approves it.
- **FR-018** A proposal MUST record the investigation that produced it, so a
  reviewer can see the evidence.
- **FR-019** Approved proposals MUST be attributed as agent-originated and
  human-approved.

**Recall discipline**

- **FR-020** Neither store MUST be pre-injected into the initial prompt.
- **FR-021** Root-agent guidance MUST instruct topology query after an affected
  service is identified, and knowledge search after concrete symptoms exist.
- **FR-022** Both MUST be exposed as declared capabilities with full metadata.
- **FR-023** Every query MUST be recorded in the run trace.

**Ablation and isolation**

- **FR-024** Independent team-scoped switches MUST disable topology and knowledge
  base retrieval.
- **FR-025** Both stores MUST be scoped by org and team.

### Key entities

| Entity | Description |
|---|---|
| **ServiceNode** | Type, name, environment, owner, annotations |
| **DependencyEdge** | Kind, direction, metadata, verification timestamp |
| **BlastRadius** | Bounded transitive dependent set with depth and truncation flag |
| **KnowledgeDocument** | Source, type, hierarchy position, version |
| **KnowledgeChunk** | Text, embedding, source document, section, location |
| **ProposedChange** | Agent-originated addition or amendment awaiting review |
| **DiscoverySource** | An adapter that populates topology |
| **TopologyReconciliation** | The diff applied by a discovery run |

## Success criteria

- **SC-001** Blast radius on a 10k-node graph at depth 3 completes within bounds
  and reports truncation when it applies.
- **SC-002** A topology cycle does not cause infinite traversal.
- **SC-003** Re-discovery preserves operator annotations while reconciling edges —
  verified by a fixture with both.
- **SC-004** A partially-failed discovery marks unverified edges rather than
  deleting them.
- **SC-005** Knowledge search returns citable chunks with resolvable source
  locations.
- **SC-006** A document containing a detected secret is rejected with the location
  reported.
- **SC-007** An agent-proposed change never takes effect without approval —
  asserted by attempting it.
- **SC-008** With either store disabled, investigations complete and results match
  the corresponding baseline.
- **SC-009** Topology unavailability degrades gracefully with the degradation
  visible in the trace.

## Out of scope

- Episodic memory (feature 010) and strategy synthesis (feature 011)
- Review UI (feature 021) — this feature provides the API and queue
- Approval workflow machinery (feature 015) — reused here, not rebuilt

## Clarifications

| Question | Resolution |
|---|---|
| Why is blast radius valuable enough to justify a graph? | It changes what the agent gathers. Knowing the three upstreams of a failing service focuses evidence collection; knowing the four downstreams makes the impact statement correct rather than guessed. Naming conventions are not a substitute. |
| Why must agent-proposed knowledge be reviewed? | An agent writing unreviewed knowledge that it later reads creates a self-reinforcing loop with no external correction. Human review is the loop breaker. |
| Are topology and knowledge base one feature or two? | One. They share the same recall discipline, the same ablation pattern, the same team scoping, and the same review workflow — splitting them would duplicate all four. |
| What if an operator has no topology data? | The graph is optional. Investigations run without it, degraded but functional (FR-009). Discovery adapters make population cheap for teams running Kubernetes or a service mesh. |
