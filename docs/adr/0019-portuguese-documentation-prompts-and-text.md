# ADR 0019 — Brazilian Portuguese permitted for documentation, prompts, and user-facing text

- **Status:** Accepted
- **Date:** 2026-08-27
- **Constitution impact:** Article XIII amended (v2.5.0)

## Context

ADR 0010 established an English-only policy across all surfaces. In practice, the project owner, team, and primary operational workflows operate in Brazilian Portuguese (pt-BR). While source code identifiers and git commit conventions benefit from standard English conventions, requiring all planning artifacts, specifications (`specs_v*/`), prompts, agent instructions, and user-facing text to be exclusively in English created friction and caused disconnects between real development practices and constitutional rules.

## Decision

Article XIII is amended to allow **Brazilian Portuguese (pt-BR)** or **English** for:
- Documentation, architecture notes, and ADRs
- Feature specifications, plans, tasks, and wave planning material (`specs_v*/`)
- Agent prompts, system prompts, and skill instructions
- User-facing text, console interfaces, and error messages (with i18n support)

**Source code identifiers, code comments, and commit messages** remain in **English** to maintain codebase uniformity, type safety, and standard open-source conventions.

## Rationale

- **Velocity and accuracy in planning**: Authoring domain requirements, UX specifications, and operational guidance in the team's native language improves precision and reduces cognitive load during specification and review.
- **Support for multilingual prompts & UX**: LLMs and modern SRE workflows effectively reason in Brazilian Portuguese, and user surfaces already leverage i18n catalogs (`en`, `pt-BR`).
- **Separation of concerns**: Keeping code identifiers (classes, functions, variables) and commit messages in English ensures clean interoperability with standard tooling, linters, and libraries without constraining documentation or agent interaction language.

## Consequences

**Positive**
- Specifications, wave artifacts, and prompt engineering can be authored natively in Brazilian Portuguese without constitutional violations.
- Aligns the constitution with real developer intent and project execution.
- Preserves code consistency by keeping programmatic identifiers in English.

**Negative**
- Requires contributors to be comfortable reading both English (source identifiers) and Brazilian Portuguese (documentation/specifications where chosen).
