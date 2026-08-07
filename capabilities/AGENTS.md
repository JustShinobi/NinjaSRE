# capabilities/ — the agent-callable surface

**Tier 2.** May import: `integrations`, `core`, `platform`, `config`. Must never import: `gateway`, `surfaces`.

Typed tools, methodology skills, the registry, auto-discovery, scoring, bounded
selection, and the bridges that let a capability arrive from outside this
repository. Three sources, one catalogue.

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
- A capability arriving over a wire protocol — MCP, ACP, OpenClaw →
  `protocols/`. A fourth protocol is one adapter satisfying `protocols/port.py`
  and no governance of its own: the cap, the namespacing, the classification
  gate, and the registration are applied in `protocols/catalogue.py` over
  whatever an adapter returns.

## Bridged capabilities

Two rules that are specific to a capability the repository did not declare.

- **A server's declaration of its own side effect is a suggestion.** It is shown
  to the operator and acted on by nothing. A third-party server annotating its
  `delete_everything` tool read-only must not be able to make it so, and a
  declaration nobody can verify is the same as no declaration — which Article
  III already answers.
- **Unclassified means it cannot execute.** The registration exists, is scored,
  and appears in the console awaiting a decision; its body refuses before any
  argument reaches the server, so the refusal is a property of the call rather
  than of whoever remembered to check. Everything else — guardrails, approval
  gating, the cache, the trace — reaches a bridged tool because it *is* an
  ordinary `RegisteredTool` dispatched through the ordinary path, and
  `tests/contract/protocols/` asserts that by comparison against a native one
  rather than by inspection.

Bridged names are `<server>__<tool>`. No native capability name contains `__`,
which is what makes a collision structurally impossible rather than unlikely,
and a test asserts it against the shipped catalogue.

[`docs/protocol-bridges.md`](../docs/protocol-bridges.md) is the operator's
version: registering a server, classifying its tools, and what NinjaSRE's own
MCP server does and does not expose.

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
