# Feature 003 — Capability Framework

- **Wave:** 0 — Foundation
- **Branch:** `feat/003-capability-framework`
- **Status:** Draft
- **Depends on:** 001, 002
- **Blocks:** 004, 005, 017, 024, 025, 026
- **ADRs:** [0002](../../docs/adr/0002-hybrid-capability-model.md), [0009](../../docs/adr/0009-full-integration-parity.md)

## Summary

The unified catalogue of everything the agent can do: **typed tools** for
execution and **skills** for methodology, discovered automatically, scored against
the incident, and selected under a hard per-turn bound. This is the layer that
makes a catalogue of ~85 integrations affordable in context and measurable in
trajectory.

## User scenarios

### Primary story

A contributor adds a new integration by creating one package. Its tools and its
methodology skill appear in the catalogue with no central registry edit, are
scored against relevant alerts, and are hidden from the model when irrelevant —
without reducing what is available when they are relevant.

### Acceptance scenarios

1. **Given** a new package under `capabilities/tools/` with a `@tool`-decorated
   function, **when** the registry is built, **then** the tool is discovered with
   its full metadata and no registry file was edited.
2. **Given** a `SKILL.md` with valid frontmatter, **when** the registry is built,
   **then** the skill is discovered and its metadata cost is under the configured
   token ceiling.
3. **Given** a skill that declares a tool which does not exist, **when** the
   registry is built, **then** the build fails naming the skill and the missing
   tool.
4. **Given** 400 registered capabilities and a per-turn cap of 32 schemas,
   **when** a turn is prepared, **then** at most 32 tool schemas are sent, chosen
   by relevance, with the cheap reasoning capabilities guaranteed a reserved slot.
5. **Given** a selected skill, **when** the turn is prepared, **then** the skill
   body is loaded and the tools it declares are brought into the schema set,
   still respecting the cap.
6. **Given** a tool with no `side_effect_level` declared, **when** the registry is
   built, **then** the build fails — absence is not defaulted to read.
7. **Given** a tool whose required integration is not configured for the team,
   **when** the catalogue is resolved, **then** the tool is excluded and the
   reason is recorded.
8. **Given** two tools with the same name, **when** the registry is built,
   **then** the build fails naming both source modules.

### Edge cases

- A skill whose body exceeds the context budget on its own.
- A tool whose input schema fails provider normalisation (feature 002 catches it;
  the registry must surface which tool).
- Circular skill references (skill A directs a tool that a skill B also directs —
  legal; skill A declaring skill B as a dependency that declares A — illegal).
- A capability available in one deployment profile but not another (sandbox
  profile affects which execution tools are viable).
- Selection when the alert carries no source hint at all.

## Requirements

### Functional

- **FR-001** Two capability kinds MUST exist: `Tool` (typed execution) and `Skill`
  (methodology with progressive disclosure), in one catalogue with one selection
  path.
- **FR-002** A tool MUST be declarable two ways: a `@tool(...)` decorator on a
  function, and a `BaseTool` subclass for richer behaviour.
- **FR-003** Every tool MUST declare: `name`, `display_name`, `description`,
  `input_schema` (or `input_model`), `output_schema` (or `output_model`),
  `evidence_source`, `evidence_type`, `side_effect_level`, `parallel_safe`,
  `requires`, `use_cases`, `anti_examples`, `tags`.
- **FR-004** `side_effect_level` MUST be one of: `read`, `read_sensitive`,
  `write_reversible`, `write_irreversible`, `destructive`. It MUST have no default
  — omission is a build failure.
- **FR-005** A tool above `read_sensitive` MUST declare `requires_approval=True`,
  `approval_reason`, and a rollback-plan generator (contract defined here,
  implemented in feature 017).
- **FR-006** A skill MUST be a directory containing `SKILL.md` with YAML
  frontmatter: `name`, `description`, `domain`, `directs_tools`, `applies_when`,
  optional `requires`.
- **FR-007** Skill metadata (frontmatter + description) MUST cost no more than
  `MAX_SKILL_METADATA_TOKENS` per skill. A test MUST enforce this across the
  catalogue.
- **FR-008** A skill body MUST load only when the skill is selected.
- **FR-009** A skill MUST NOT declare arbitrary shell execution as its capability.
  Its `directs_tools` entries MUST all resolve to registered tools; a dangling
  reference is a build failure.
- **FR-010** Discovery MUST walk `capabilities/tools/**`, `capabilities/skills/**`,
  and each `integrations/<vendor>/tools/` package. Adding a capability MUST NOT
  require editing a central file.
- **FR-011** Duplicate capability names MUST fail the build naming both sources.
- **FR-012** The catalogue MUST be resolvable per team: a capability whose
  `requires` are unmet is excluded with a recorded reason, surfaced in the console.
- **FR-013** Selection MUST score capabilities against the incident using: alert
  source match, `applies_when` match, tag overlap, use-case similarity, historical
  effectiveness (feature 010 once available), and explicit plan entries.
- **FR-014** Selection MUST enforce `MAX_AGENT_TOOL_SCHEMAS` and MUST reserve
  `MAX_SECONDARY_FALLBACK_TOOLS` slots for cheap reasoning and knowledge
  capabilities so they are never crowded out.
- **FR-015** Selecting a skill MUST bring its `directs_tools` into the turn's
  schema set, subject to the same cap.
- **FR-016** Every capability invocation MUST emit a telemetry record into the run
  trace: name, arguments (guardrail-filtered), duration, outcome, evidence
  produced, and error classification on failure.
- **FR-017** A capability error MUST be returned as a structured result the loop
  can reason about, never as an unhandled exception.
- **FR-018** Capability metadata MUST be exposed through a read API for the
  console catalogue and for documentation generation.
- **FR-019** A scaffold command MUST generate a complete capability package: tool
  module, `SKILL.md`, contract test, and provenance header.
- **FR-020** Prose fields (`use_cases`, `anti_examples`, `examples`) MUST NOT use
  implicit string concatenation inside list literals; long strings MUST be module
  constants.

### Key entities

| Entity | Description |
|---|---|
| **Capability** | The common supertype of Tool and Skill in the catalogue |
| **Tool** | Typed execution unit with schema, side-effect level, and evidence contract |
| **Skill** | Methodology document with cheap metadata, on-demand body, and declared tool bindings |
| **CapabilityMetadata** | The declarative record used for scoring, selection, approval, and documentation |
| **Registry** | The discovered, validated, deduplicated catalogue |
| **ResolvedCatalogue** | The registry filtered to what a specific team has configured |
| **SelectionResult** | The bounded per-turn set of schemas plus loaded skill bodies, with the rationale |

## Success criteria

- **SC-001** With 400 capabilities registered, per-turn schema payload never
  exceeds the cap, and the reserved secondary slots are always populated.
- **SC-002** Total catalogue metadata cost for ~85 integrations stays under the
  configured metadata budget — measured by a test, not estimated.
- **SC-003** Adding a capability requires creating exactly one package and editing
  zero existing files. Proven by the scaffold command plus a test.
- **SC-004** Every build failure mode (dangling tool reference, duplicate name,
  missing `side_effect_level`, oversized metadata) is covered by a fixture test
  producing a distinct message.
- **SC-005** Selection is deterministic: the same incident and catalogue produce
  the same selection, verified by a golden test.
- **SC-006** A capability invocation trace is sufficient to reconstruct the call
  without access to the process — verified by replaying a trace.

## Out of scope

- The loop that consumes selections (feature 004)
- The planning stage that seeds selection (feature 005)
- Approval execution (feature 017)
- Individual integrations (features 024–025)

## Clarifications

| Question | Resolution |
|---|---|
| Can a skill exist without tools? | Yes — pure methodology skills (investigation framework, remediation discipline) direct no tools and shape reasoning only. `directs_tools` may be empty. |
| Can a tool exist without a skill? | Yes, but Wave 6 parity requires every integration to ship at least one methodology skill. Utility tools may stand alone. |
| How does historical effectiveness enter scoring before feature 010 exists? | The scorer takes an `EffectivenessProvider` port with a neutral default. Feature 010 supplies the real one. |
| Where do remediation tools live? | `capabilities/tools/remediation/` — cross-vendor by nature, all above `read_sensitive`, all approval-gated. |
