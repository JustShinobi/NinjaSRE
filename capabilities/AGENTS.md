# capabilities/ — the agent-callable surface

**Tier 2.** May import: `integrations`, `core`, `platform`, `config`. Must never import: `gateway`, `surfaces`.

Typed tools, methodology skills, the registry, auto-discovery, scoring, and
bounded selection. Two layers, one catalogue.

## Conventions

- Every capability carries full declarative metadata: input schema, evidence
  source, `side_effect_level`, `parallel_safe`, approval requirements, use cases,
  and anti-examples (Article IX).
- A missing `side_effect_level` means *write*, not read. Absence is never
  permission.
- A skill carries methodology and declares the tools it directs. It is never a
  wrapper for arbitrary shell execution against production.
- Adding a capability never edits a central registry file — discovery walks the
  owning package.
- Selection is scored and capped. Sending the whole catalogue is not a strategy.

## Where things go

- Typed execution → `tools/<domain>/`.
- Methodology, with progressive disclosure → `skills/<skill-id>/SKILL.md`.
- Discovery, scoring, and selection → `registry/`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `capabilities/`.
