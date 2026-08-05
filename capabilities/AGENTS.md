# capabilities/ — the agent-callable surface

**Tier 2.** May import: `integrations`, `core`, `platform`, `config`. Must never import: `gateway`, `surfaces`.

Typed tools, methodology skills, the registry, auto-discovery, scoring, and
bounded selection. Two layers, one catalogue.

## Conventions

- Every capability carries full declarative metadata: input schema, evidence
  source, `side_effect_level`, `parallel_safe`, approval requirements, use cases,
  and anti-examples (Article IX).
- **`side_effect_level` has no default.** A tool that does not declare one
  cannot be constructed, so the omission is a build failure rather than a quiet
  promotion to read. A capability arriving from outside the repository with no
  declaration at all is treated as a write.
- Anything above `read_sensitive` also declares `requires_approval`, an
  `approval_reason`, and a rollback plan or planner. The metadata type checks
  the three together, because the approval gate is too late to find one missing.
- A skill carries methodology and declares the tools it directs. It is never a
  wrapper for arbitrary shell execution against production — the build lints
  bodies for instructions to run commands.
- Adding a capability never edits a central registry file. Discovery walks
  `tools/**`, `skills/**`, and each `integrations/<vendor>/tools/`, so a new
  capability is one new package.
- Selection is scored, deterministic, and capped. Sending the whole catalogue is
  not a strategy, and neither is an LLM ranker: selection runs before every turn
  and has to produce the same answer twice for trajectory evaluation to mean
  anything.

## Where things go

- Typed execution → `tools/<domain>/`. A tool reaching exactly one vendor
  belongs in `integrations/<vendor>/tools/` instead.
- Methodology, with progressive disclosure → `skills/<skill-id>/SKILL.md`.
- Discovery, validation, scoring, and selection → `registry/`.

## The two budgets

A skill's frontmatter and description are in context on **every** turn, for
every skill the team has — that is what `MAX_SKILL_METADATA_TOKENS` bounds, and
`MAX_CATALOGUE_METADATA_TOKENS` bounds their sum. A skill body and a tool
description are paid for only when selected, and selection is capped, so those
scale with the cap rather than with the catalogue.

Both ceilings are measured by a test against the shipped catalogue rather than
estimated.

## Scaffolding

```bash
uv run python tools/scaffold_capability.py <tool_name> --domain <domain> [--vendor <vendor>]
```

Writes the tool module, the `SKILL.md`, and the contract test, and edits
nothing.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `capabilities/`.
