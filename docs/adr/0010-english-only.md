# ADR 0010 — English-only codebase and documentation

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article XIII

## Context

The project owner works in Brazilian Portuguese. NinjaSRE derives from two
English-language open-source projects and is intended to be open source itself.

The choice spans several surfaces that could in principle diverge: source
identifiers and comments, commit messages, specification documents, agent system
prompts, user-facing product text, and the public README.

## Decision

**Everything is in English**: source, comments, identifiers, commit messages,
specifications, ADRs, agent prompts, console UI text, CLI output, and
documentation.

## Rationale

**Derived content is already English.** The provenance map targets substantial
reuse — the pipeline design's domain modules, guardrails, masking, and scenario corpus;
The memory design's memory models, config hierarchy, and ~51 SKILL.md methodology documents.
Translating them would fork them from their origin, making future backports
impractical for no functional gain.

**Prompts are load-bearing and English-tuned.** The SKILL.md methodology content
and the investigation system prompts are the product's accumulated reasoning
quality. Model performance on English instructions is the best-characterised case,
and the synthetic scenario answer keys — `required_keywords`,
`ruling_out_keywords`, `forbidden_categories` — are English token matches.
Translating prompts while keeping English answer keys would break the evaluation
suite; translating both would invalidate every baseline.

**Contribution surface.** Open-source SRE tooling draws contributors globally.
English source and specs keep that door open.

**Consistency avoids the worst outcome.** Mixed-language codebases drift: PT-BR
comments on English identifiers, specs that describe an English UI in Portuguese.
A single language removes the ambiguity about which surface uses which.

**Bilingual documentation was considered and rejected** for the usual reason: two
versions of a specification diverge, and the divergence is discovered when someone
implements the stale one.

## Consequences

**Positive**

- Reused code and prompts reused verbatim; backports stay feasible
- Evaluation baselines remain valid
- Open to international contribution
- No translation maintenance burden

**Negative**

- The project owner works in a second language on their own project
- Portuguese-speaking operators read English documentation

**Mitigations**

- Conversation about the work happens in Portuguese; the artefacts are English.
  These are separate concerns
- Product UI is built with i18n scaffolding from the start, so a `pt-BR` locale
  can be added later without refactoring — a translated *interface* is a feature,
  distinct from a translated *codebase*
- The documentation site is structured for community translation of user-facing
  guides, with English as the normative source
