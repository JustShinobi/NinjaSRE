# Plan — 003 Capability Framework

## Summary

Build the unified capability catalogue: framework primitives in `core/capability/`
(tier 3), discovery, validation, scoring, and bounded selection in
`capabilities/registry/` (tier 2). Adopt Tracer's tool framework and registry
discovery; adopt Swapnil's progressive disclosure; add the skill↔tool binding
contract that makes the hybrid model safe.

## Technical context

| Aspect | Choice |
|---|---|
| Tool declaration | `@tool(...)` decorator and `BaseTool` subclass, both producing a `RegisteredTool` |
| Schema source | Explicit `input_schema` dict or a Pydantic `input_model` (generating the schema) |
| Skill format | Directory with `SKILL.md`, YAML frontmatter, Markdown body |
| Discovery | `pkgutil.walk_packages` over declared roots; module attribute scan |
| Validation | Build-time, failing loudly — a broken catalogue must never reach runtime |
| Token measurement | The active provider's tokeniser via `core.llm.count_tokens` |
| Scoring | Deterministic weighted scoring; no LLM call in the selection path |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | FR-016 — every invocation produces a trace record sufficient to reconstruct it (SC-006) |
| II | FR-014 — the schema cap and secondary reserve are named constants |
| III | FR-004, FR-005 — `side_effect_level` mandatory with no default; approval metadata required above `read_sensitive` |
| IV | Tools reach externals only via integration clients, which are proxy-only (feature 007) |
| V | The catalogue is runtime-agnostic |
| VI | Schemas pass through the normaliser (feature 002); no provider-specific capability shape |
| VII | The scorer takes an `EffectivenessProvider` port so feature 010 can feed learned signal, and ablation can neutralise it |
| VIII | `core/capability/` tier 3; `capabilities/` tier 2; `integrations` never imports `capabilities` |
| IX | **This is the feature.** FR-001 to FR-020 |
| X | No capability transmits off-host by construction |
| XI | Trace records persist through `RunTraceStore` |
| XII | Every build-failure mode has a fixture test written first (SC-004) |
| XIII | Provenance headers; skill content ported from Swapnil is attributed |

**Violations:** none.

## Project structure

```
core/capability/                 # tier 3 — framework primitives
├── types.py                     # Capability, Tool, Skill protocols
├── metadata.py                  # CapabilityMetadata, SideEffectLevel, EvidenceType
├── decorator.py                 # @tool
├── base.py                      # BaseTool
├── registered.py                # RegisteredTool
├── schema.py                    # input/output schema derivation from models
├── result.py                    # CapabilityResult, structured error shapes
├── telemetry.py                 # invocation trace records
└── ports.py                     # EffectivenessProvider, IntegrationAvailability

capabilities/                    # tier 2 — the catalogue
├── registry/
│   ├── discovery.py             # package walk over tools, skills, integration tools
│   ├── validation.py            # duplicates, dangling refs, missing metadata, token budget
│   ├── catalogue.py             # Registry, ResolvedCatalogue
│   ├── disclosure.py            # skill metadata vs body loading
│   ├── scoring.py               # weighted relevance scoring
│   ├── selection.py             # cap enforcement, secondary reserve, skill→tool expansion
│   └── api.py                   # read API for console and docs generation
├── skills/
│   ├── _templates/              # domain templates: logstore, metrics, tracing,
│   │                            #   cloud-control-plane, database, vcs, ticketing
│   ├── investigate/SKILL.md     # core methodology
│   ├── observability/SKILL.md
│   ├── infrastructure/SKILL.md
│   └── remediation/SKILL.md
├── tools/
│   ├── system/                  # no vendor: guidance, memory, python execution
│   ├── remediation/             # cross-vendor write actions
│   └── cross_vendor/
└── protocols/                   # MCP/ACP bridges (feature 026)
```

## The skill↔tool contract

The single most important invariant in this feature.

```yaml
# capabilities/skills/observability-datadog/SKILL.md frontmatter
name: observability-datadog
description: Datadog log, metric, and APM investigation. Statistics before samples.
domain: observability
applies_when:
  alert_sources: [datadog]
  tags: [logs, metrics, apm]
directs_tools:
  - datadog_log_statistics
  - datadog_sample_logs
  - datadog_query_metrics
  - datadog_list_monitors
requires:
  integrations: [datadog]
```

Rules enforced at build time:

1. Every entry in `directs_tools` resolves to a registered tool (FR-009).
2. The skill's `requires` is a subset of the union of its tools' `requires`.
3. Metadata token cost is under the ceiling (FR-007).
4. The body contains no instruction to execute shell against production.

Rule 4 is checked by a lint pass over the body looking for the anti-patterns
inherited from the upstream skill format (direct `python script.py` invocations
against live systems). Ported skills are rewritten to reference tools instead.

## Scoring model

Deterministic, no LLM in the path.

| Signal | Weight | Source |
|---|---|---|
| Alert-source match | high | `applies_when.alert_sources` vs the alert's source |
| Explicit plan entry | highest | `plan_evidence` stage output (feature 005) |
| Tag overlap | medium | Capability tags vs extracted alert tags |
| Use-case similarity | medium | Lexical match against `use_cases` |
| Historical effectiveness | medium | `EffectivenessProvider` (feature 010) |
| Anti-example match | negative | `anti_examples` matching the alert suppresses the capability |
| Availability | gate | Unmet `requires` excludes entirely |

Selection then:

1. Takes explicit plan entries first.
2. Fills by score down to `MAX_AGENT_TOOL_SCHEMAS - MAX_SECONDARY_FALLBACK_TOOLS`.
3. Reserves the remaining slots for cheap reasoning and knowledge capabilities.
4. Expands selected skills into their `directs_tools`, re-applying the cap.
5. Records the full rationale into the trace.

## Implementation phases

### Phase 1 — Primitives (test-first)
`types.py`, `metadata.py`, `result.py`, `ports.py`. `SideEffectLevel` with no
default. Tests for every validation failure mode, all red.

### Phase 2 — Declaration
`decorator.py`, `base.py`, `registered.py`, `schema.py`. Both declaration styles
produce identical `RegisteredTool` records.

### Phase 3 — Skills and disclosure
`SKILL.md` parsing, frontmatter schema, `disclosure.py` splitting metadata from
body, token-cost measurement.

### Phase 4 — Discovery and validation
Package walk, duplicate detection, dangling-reference detection, metadata budget
enforcement, shell-anti-pattern lint. Phase 1 tests turn green here.

### Phase 5 — Resolution and scoring
`ResolvedCatalogue` per team, the weighted scorer, golden determinism test.

### Phase 6 — Selection
Cap enforcement, secondary reserve, skill expansion, rationale recording.
SC-001 test with 400 synthetic capabilities.

### Phase 7 — Surface and tooling
Read API, scaffold command, documentation generation, core methodology skills
ported from Swapnil.

## Complexity tracking

| Item | Justification |
|---|---|
| Two tool declaration styles | Upstream precedent shows both are used heavily: the decorator for the ~80% simple case, the base class where a tool needs lifecycle or shared state. Both funnel to one `RegisteredTool`, so downstream code sees one shape. |
| Build-time validation that hard-fails | A dangling skill→tool reference at runtime is an incident during an incident. Failing the build is the only acceptable time to discover it. |
| Anti-pattern lint on skill bodies | Mechanical, but it is what keeps ADR 0002's safety property true as ~85 skills are ported from a format that permitted arbitrary shell. |
| Deterministic scorer rather than an LLM ranker | An LLM in the selection path would make trajectory evaluation non-reproducible and add a call before every turn. Determinism is required by SC-005. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `core/tool_framework/` | ADAPT → `core/capability/` |
| Tracer | `tools/registry_discovery.py`, `registry.py`, `registry_index.py` | ADAPT → `capabilities/registry/` |
| Tracer | `core/tool_framework/skill_guidance.py` | ADAPT → binding contract |
| Tracer | `core/tool_framework/telemetry.py` | ADOPT |
| Tracer | `core/domain/alerts/tool_planning.py` scoring | ADOPT → `scoring.py` |
| Tracer | `tools/investigation/stages/gather_evidence/tools.py` cap logic | ADOPT → `selection.py` |
| Swapnil | Progressive disclosure (metadata-then-body) | ADOPT → `disclosure.py` |
| Swapnil | `sre-agent/.claude/skills/*/SKILL.md` | ADAPT → `capabilities/skills/` with tool bindings replacing shell invocations |
| Swapnil | `.claude/skills/investigate/SKILL.md` 5-phase methodology | ADAPT → `capabilities/skills/investigate/` |

## Risks

| Risk | Mitigation |
|---|---|
| Skill bodies ported from upstream retain shell instructions | The anti-pattern lint fails the build; porting is not complete until it passes |
| Metadata budget exceeded as the catalogue reaches 85 integrations | SC-002 measures it continuously; the budget is a named constant that can be raised deliberately with a recorded rationale |
| Scoring quality is poor without historical data | The `EffectivenessProvider` port defaults neutral, so selection degrades to source and tag matching — which is Tracer's current behaviour, a known-adequate baseline |
| Cap still hides relevant capabilities at 85 integrations | Progressive disclosure means skills, not tools, compete for the metadata budget; the cap applies to expanded tool schemas per turn, which is a much smaller working set |
