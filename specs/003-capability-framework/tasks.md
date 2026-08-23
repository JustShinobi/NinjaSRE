# Tasks — 003 Capability Framework

## Phase 1 — Primitives (test-first)

- **T001** `core/capability/metadata.py`: `SideEffectLevel` (`read`,
  `read_sensitive`, `write_reversible`, `write_irreversible`, `destructive`),
  `EvidenceType`, `EvidenceSource`, `CapabilityMetadata` with **no default** for
  `side_effect_level`.
- **T002** `core/capability/types.py`: `Capability`, `Tool`, `Skill` Protocols,
  docstring-only bodies.
- **T003** `core/capability/result.py`: `CapabilityResult` with success and
  structured-error variants; errors are values, never exceptions (FR-017).
- **T004** `core/capability/ports.py`: `EffectivenessProvider` (neutral default),
  `IntegrationAvailability`.
- **T005** Write validation failure fixtures (all red): dangling skill→tool ref,
  duplicate name, missing `side_effect_level`, oversized skill metadata, shell
  anti-pattern in a skill body, approval metadata missing above `read_sensitive`.

## Phase 2 — Declaration

- **T006** `core/capability/registered.py`: `RegisteredTool`, the attribute marker
  used by discovery.
- **T007** `core/capability/decorator.py`: `@tool(...)` with full typed overloads.
- **T008** `core/capability/base.py`: `BaseTool`.
- **T009** `core/capability/schema.py`: derive `input_schema`/`output_schema` from
  Pydantic models; validate hand-written schemas.
- **T010** Test: decorator and base class produce equivalent `RegisteredTool`
  records for the same declaration.
- **T011** `core/capability/telemetry.py`: invocation record with name, filtered
  arguments, duration, outcome, evidence, error class (FR-016).
- **T012** Test: a trace record is sufficient to reconstruct the call (SC-006).
- **T013** Lint rule for FR-020 (no implicit string concatenation in metadata list
  literals), wired into `make verify`.

## Phase 3 — Skills and progressive disclosure

- **T014** Skill frontmatter schema: `name`, `description`, `domain`,
  `applies_when`, `directs_tools`, `requires`.
- **T015** `capabilities/registry/disclosure.py`: parse `SKILL.md`, split metadata
  from body, load body only on selection (FR-008).
- **T016** Token-cost measurement using `core.llm.count_tokens`.
- **T017** Test enforcing `MAX_SKILL_METADATA_TOKENS` per skill (FR-007).
- **T018** Test enforcing the catalogue-wide metadata budget (SC-002).
- **T019** Skill-body anti-pattern lint: reject instructions to execute shell
  against production systems.

## Phase 4 — Discovery and validation

- **T020** `capabilities/registry/discovery.py`: walk `capabilities/tools/**`,
  `capabilities/skills/**`, `integrations/*/tools/`.
- **T021** [P] Duplicate-name detection naming both source modules (FR-011).
- **T022** [P] Dangling `directs_tools` detection naming skill and tool (FR-009).
- **T023** [P] Missing-metadata detection, including the mandatory
  `side_effect_level` (FR-004).
- **T024** [P] Approval-metadata requirement above `read_sensitive` (FR-005).
- **T025** [P] Skill `requires` ⊆ union of directed tools' `requires`.
- **T026** `capabilities/registry/validation.py` composing all checks into one
  build-time gate.
- **T027** Confirm all Phase 1 fixtures now produce distinct named failures
  (SC-004).

## Phase 5 — Resolution and scoring

- **T028** `capabilities/registry/catalogue.py`: `Registry` build with caching.
- **T029** `ResolvedCatalogue`: filter by team integration availability, recording
  the exclusion reason per capability (FR-012).
- **T030** `capabilities/registry/scoring.py`: weighted scorer over alert-source
  match, `applies_when`, tag overlap, use-case similarity, effectiveness,
  anti-example suppression.
- **T031** Golden determinism test: same incident + catalogue → identical ranking
  (SC-005).
- **T032** Test: `EffectivenessProvider` neutral default degrades scoring to
  source/tag matching without error.

## Phase 6 — Selection

- **T033** `capabilities/registry/selection.py`: plan entries first, then score
  order.
- **T034** Enforce `MAX_AGENT_TOOL_SCHEMAS` (FR-014).
- **T035** Reserve `MAX_SECONDARY_FALLBACK_TOOLS` for cheap reasoning and
  knowledge capabilities; test that they are never crowded out.
- **T036** Skill expansion: bring `directs_tools` into the schema set, re-applying
  the cap (FR-015).
- **T037** Record the full selection rationale into the trace.
- **T038** SC-001 test: generate 400 synthetic capabilities; assert the cap holds
  and the reserve is populated.

## Phase 7 — Surface, tooling, and seed content

- **T039** `capabilities/registry/api.py`: read API for the console catalogue and
  documentation generation (FR-018).
- **T040** Documentation generator emitting a capability reference page from
  metadata.
- **T041** `tools/scaffold_capability.py`: generate tool module + `SKILL.md` +
  contract test + provenance header (FR-019).
- **T042** SC-003 test: scaffold a capability, assert it appears in the registry
  with zero edits to existing files.
- **T043** Domain skill templates under `capabilities/skills/_templates/`:
  logstore, metrics, tracing, cloud-control-plane, database, vcs, ticketing.
- **T044** Port `capabilities/skills/investigate/SKILL.md` — the five-phase
  methodology — from Swapnil, rewritten to reference tools.
- **T045** [P] Port `observability/SKILL.md`, `infrastructure/SKILL.md`,
  `remediation/SKILL.md`.
- **T046** [P] `capabilities/tools/system/`: guidance tool, memory tool stub
  (feature 010 fills it), Python execution tool with sandbox binding.
- **T047** `capabilities/tools/remediation/` contracts: restart, rollback, scale —
  all `write_reversible` or above, all `requires_approval`, all with rollback-plan
  generators (implementation in feature 017).
- **T048** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] 400-capability cap and reserve test green (SC-001)
- [ ] Catalogue metadata budget test green (SC-002)
- [ ] Zero-edit capability addition proven (SC-003)
- [ ] All six build-failure modes produce distinct messages (SC-004)
- [ ] Selection determinism golden test green (SC-005)
- [ ] Trace-replay reconstruction test green (SC-006)
- [ ] No skill body instructs shell execution against production
- [ ] `make verify` green
