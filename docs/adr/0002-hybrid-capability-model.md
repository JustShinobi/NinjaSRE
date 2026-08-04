# ADR 0002 — Hybrid capability model: skills for methodology, tools for execution

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article IX

## Context

The two prior systems take opposite approaches to extending what the agent can do.

**The pipeline design — typed tools.** Every capability is a `@tool`-decorated function or
`BaseTool` subclass carrying a JSON Schema, evidence source, side-effect level,
use cases, and anti-examples. A registry auto-discovers them; a planner scores
them against the alert and hands a bounded shortlist to the loop.

*Strength:* the planner can reason about capabilities before invoking them, the
trajectory is a sequence of named actions (so it can be scored against a golden
trajectory), and side effects are declared.
*Weakness:* schema payload grows with catalogue size — mitigated there by a
hard cap of 32 schemas per turn, which silently hides capabilities. Each
integration costs significant code.

**The memory design — skills.** Each capability is a `SKILL.md` with YAML frontmatter plus
Python scripts. The SDK loads ~100 tokens of metadata per skill and the full body
only on demand; scripts run via `Bash`.

*Strength:* progressive disclosure makes 51 skills cost less context than 20 tool
schemas. The SKILL.md files carry real investigation methodology — "statistics
before samples", decision flowcharts, anti-patterns, query-language reference —
which is the single most valuable content asset across both repos.
*Weakness:* the executable surface is arbitrary shell. The planner cannot score
it, the trajectory is not a sequence of named actions, side effects are
undeclared, and approval gating is impossible.

## Decision

**Both layers, one catalogue.**

- A **skill** is the methodology layer: domain investigation guidance with
  progressive disclosure. It declares which tools it directs. It does not execute
  arbitrary shell against production.
- A **tool** is the execution layer: typed input schema, declared evidence
  source, `side_effect_level`, `parallel_safe`, approval requirements.
- Both are auto-discovered and appear in a single scored catalogue. Selecting a
  skill loads its body and brings its declared tools into the turn's schema set.

## Rationale

The two weaknesses cancel.

**Progressive disclosure fixes the schema cap.** The pipeline design's 32-schema ceiling exists
because sending every tool's schema every turn is unaffordable. With skills
carrying cheap metadata and tools loaded only when their skill is selected, the
effective catalogue can be far larger than the per-turn schema budget without
hiding capabilities from the planner.

**Typed tools fix the unplannability.** Trajectory evaluation — the mechanism that
makes Article VII's "learning is measured" enforceable — requires the agent's
actions to be a sequence of named, comparable operations. Shell invocations are
not. Making execution typed is a precondition for the evaluation half of the
product.

**Methodology is separable from execution.** The insight from reading the memory design's
SKILL.md files is that their value is not the scripts — it is the prose telling
the agent *how to think about* Datadog, or Kubernetes, or a slow query. That prose
composes perfectly with typed execution.

**Side-effect declaration becomes possible.** Article III requires every capability
to declare its side-effect level. A shell script cannot; a typed tool must.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Tools only | Loses the methodology content and the context economics; forces the schema cap to hide capabilities as the catalogue grows to ~85 integrations |
| Skills only | Makes trajectory scoring, capability planning, approval gating, and side-effect classification impossible — removing the product's differentiator |
| Tools + MCP only | MCP is a valuable extension path (see ADR for protocol bridges) but delegates methodology and side-effect declaration to third parties we do not control |

## Consequences

**Positive**

- Large catalogue without proportional context cost
- Full trajectory observability and scoring
- Approval and side-effect governance apply uniformly
- Skill authoring stays low-friction for contributors

**Negative**

- Two artefact types to author, document, and test per integration
- A binding contract between skills and tools must be validated (a skill
  referencing a non-existent tool is a build error)
- Migration of ~250 prior skill scripts into typed tools is significant work

**Mitigations**

- Scaffold generator emits skill + tools + verifier + contract test together
- Registry validation fails the build on dangling skill→tool references
- Tier-1 integrations get hand-curated methodology; the rest are generated from
  prior content and promoted on demand
