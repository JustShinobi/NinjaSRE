# Tasks — 012 Knowledge Graph and Knowledge Base

## Phase 1 — Models and contracts (test-first)

- **T001** `topology/models.py`: `ServiceNode`, `DependencyEdge` with kind and
  verification timestamp, `BlastRadius` with truncation flag (FR-001, FR-002).
- **T002** `base/models.py`: `KnowledgeDocument`, `KnowledgeChunk`, tree node.
- **T003** `platform/knowledge/policy.py`: independent ablation switches for
  topology and knowledge base (FR-024).
- **T004** Write the cycle test: `A → B → A` traversal terminates (SC-002). Red.
- **T005** Write the reconciliation test: annotations preserved, stale edges
  removed (SC-003). Red.
- **T006** Write the degraded-discovery test: unverified marking, no deletion
  (SC-004). Red.
- **T007** Write the approval-bypass test: no path from proposal to knowledge base
  without review (SC-007). Red.
- **T008** Write the secret-rejection test with location reporting (SC-006). Red.

## Phase 2 — Topology core

- **T009** `topology/queries.py`: thin wrapper over the `TopologyGraph` port; only
  the fixed catalogue (FR-003).
- **T010** Bounded traversal with `MAX_GRAPH_DEPTH` and `MAX_GRAPH_RESULTS`;
  truncation reported in the result (FR-004).
- **T011** Cycle-safe traversal with a visited set (FR-005); confirm SC-002.
- **T012** Empty result for an unknown service, cleanly (acceptance scenario 2).
- **T013** Graceful degradation when the graph is unavailable, recorded in the
  trace (FR-009); confirm SC-009.
- **T014** Verification timestamps surfaced with every result.

## Phase 3 — Topology population

- **T015** `topology/import_.py`: declarative topology-as-code with schema
  validation (FR-006).
- **T016** `topology/discovery/port.py`: `DiscoverySource` protocol with a health
  signal.
- **T017** `topology/discovery/kubernetes.py`: services, endpoints, owner
  references.
- **T018** [P] `topology/discovery/mesh.py`: service-mesh telemetry.
- **T019** [P] `topology/discovery/traces.py`: trace-derived dependencies.
- **T020** `topology/reconciliation.py`: the three-way merge table from the plan
  (FR-007).
- **T021** Operator annotations always preserved; operator-authored edges never
  removed by discovery; confirm SC-003.
- **T022** Degraded-source path marking edges unverified rather than deleting
  (FR-008); confirm SC-004.
- **T023** Reconciliation diff recorded for audit.

## Phase 4 — Knowledge ingestion

- **T024** `base/chunking.py`: section-aware chunking with overlap and bounded
  chunk size (FR-011).
- **T025** Oversized-document handling: split across chunks preserving section
  identity.
- **T026** `base/ingestion.py`: chunk, embed, persist with source document and
  location.
- **T027** Guardrail screening on ingestion; reject documents with detected
  secrets, reporting the location (FR-015); confirm SC-006.
- **T028** `base/tree.py`: document hierarchy with team scoping (FR-012).
- **T029** Document types: runbook, postmortem, architecture note, procedure
  (FR-010).
- **T030** Versioning: re-ingesting a document supersedes rather than duplicates.

## Phase 5 — Knowledge search

- **T031** `base/search.py`: vector search over chunks, team-scoped.
- **T032** Results carry source document, section, and a resolvable link so the
  agent can cite (FR-013); confirm SC-005.
- **T033** Empty-result handling as a normal outcome.
- **T034** Cross-team isolation test (FR-025).

## Phase 6 — Capabilities and proposals

- **T035** `capabilities/tools/system/topology_query/tool.py`: typed capability,
  `side_effect_level=read`, full metadata (FR-022).
- **T036** [P] `capabilities/tools/system/knowledge_search/tool.py`.
- **T037** `platform/knowledge/proposals.py`: proposal model recording the
  originating investigation (FR-016, FR-018).
- **T038** Review queue over feature 015's approval machinery (FR-017).
- **T039** `capabilities/tools/system/knowledge_propose/tool.py`: proposal-only;
  no write path to the knowledge base.
- **T040** Confirm SC-007: no code path applies a proposal without approval.
- **T041** Attribution on approval: agent-originated, human-approved (FR-019).
- **T042** Root-prompt guidance for both stores, appended at `on_run_start`
  (FR-020, FR-021).
- **T043** Query recording in the run trace for both capabilities (FR-023).

## Phase 7 — Sync, ablation, scale

- **T044** [P] `base/sync/confluence.py`.
- **T045** [P] `base/sync/notion.py`.
- **T046** [P] `base/sync/google_docs.py`.
- **T047** [P] `base/sync/git.py`: Markdown from a repository.
- **T048** Sync scheduling via feature 016's scheduler.
- **T049** Wire independent ablation switches into both retrieval paths; confirm
  SC-008.
- **T050** Register topology and knowledge base as separate ablation axes for
  feature 028.
- **T051** Seed a 10k-node graph; validate depth-3 blast radius within bounds and
  truncation reporting (SC-001).
- **T052** Operator documentation: populating topology, authoring runbooks,
  reviewing agent proposals, disabling either store.
- **T053** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] 10k-node depth-3 blast radius within bounds, truncation reported (SC-001)
- [ ] Cycles terminate (SC-002)
- [ ] Reconciliation preserves annotations (SC-003)
- [ ] Degraded discovery marks rather than deletes (SC-004)
- [ ] Knowledge results are citable with resolvable locations (SC-005)
- [ ] Secret-bearing documents rejected with location (SC-006)
- [ ] No proposal reaches the knowledge base without approval (SC-007)
- [ ] Both stores independently ablatable to baseline (SC-008)
- [ ] Graph unavailability degrades gracefully (SC-009)
- [ ] `make verify` green
