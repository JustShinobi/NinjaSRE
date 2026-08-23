# Plano — 059 Team operating context

## The gap, located

`platform/config_service/schema/agents.py` is exactly as the spec describes:
`PromptOverrides` (three closed fields — investigator, intake, diagnose,
"a role nobody declared is a prompt nobody sends") and
`AgentsConfig.prompt_for(role)` returning the override **or**
`DEFAULT_RUNTIME_SYSTEM_PROMPT` — replace-or-default, nothing additive. The
config sections already inherit through the tree with provenance
(`Hierarchy.layers` root-first deep merge, `platform/config_service/`), so
"per node, inherited, attributed" is the existing machinery — the feature is
one new section plus its assembly, bounds, and screen.

## Escopo A — the additive field

`AgentsConfig` gains `operating_context: OperatingContext`, a new
`ConfigSection`:

- **Named sections** (`tuple[ContextSection, ...]`, each `name` + `body`),
  because a section is the unit of inheritance: a child node can add,
  override (same name), or remove (empty body at the child — the
  clear-to-inherit semantics 058 built) one section without touching the
  rest. A single text blob could only be replaced whole — the exact failure
  this spec exists to fix, one level down.
- Distinct names enforced by a validator (the `_names_are_distinct`
  pattern already in `AgentsConfig`).

**Assembly**: `prompt_for(role)` (or the run-composition site that calls it
— wherever the prompt is finally assembled for the model) appends the
rendered context *after* the shipped-or-overridden prompt, under a fixed
heading, for **every role that investigates** (investigator and subagents;
intake/diagnose excluded by default — classification does not need estate
facts and pays for them on every alert; a constant names the included
roles). Acceptance 1's test asserts both the distributed prompt and the
context reach the model in one message — driven through a scripted
`core.llm` client, not by inspecting config.

## Escopo B — bounds

- **Token budget**: `OPERATING_CONTEXT_TOKEN_BUDGET` in
  `config/constants/agents.py`. Exceeding it is a *validation error at
  write time* naming the overage in tokens — never truncation (the
  spec's rule; contrast deliberately recorded here with
  `core/agent/context_budget.py`, which truncates *evidence* at run time —
  context is configuration, and configuration that silently shrinks is
  configuration nobody can reason about). Counting uses the same estimator
  the budget policy uses, so the two never disagree about what a token is.
- **No secrets**: section bodies pass the guardrail ruleset + masking
  detectors (the `platform/estate/attributes.screened` /
  knowledge-ingestion pattern) at validation; a match refuses the write
  naming the rule and location, value unlogged — same contract as 056's
  ingestion refusal.
- **Fact, not instruction**: stated in the UI copy and exemplified by the
  template (Scope C). Deliberately *not* enforced by classifier — a model
  call that polices prose is a guess with a veto, and the constitution's
  Article I.4 posture (say what you cannot determine) argues against
  pretending to know. The screen says the rule; runbooks (056) and policy
  (058) are linked as the right homes for instructions.

## Escopo C — the derived template

A starting document generated server-side when the section list is empty:
zones with their CIDRs (053's `ZoneMap`), signal sources per question
(054's map — including the LXC-metrics-from-host fact, which ships in the
template *text* so it lands even before an operator writes anything),
criticality semantics (from the enrichment's presence), and empty prompts
for what only humans know (who is called, what matters). Derivation is
data-assembly only — no LLM (the spec's out-of-scope, structural here: the
template builder has no `get_llm` import, testable).

## Escopo D — the screen

A settings-area screen (D2's `Contexto da equipe` slot) using 058's editor
pattern: sections editable per node, provenance shown per section (which
level set it), and **the preview is the final text** — the exact string the
model will receive, rendered before save (the 058 discipline; here the
"effect" is literally the prompt suffix). The budget meter shows tokens
used/available as the operator types.

## O que esta feature NÃO faz

- No per-investigation context (that is the incident description).
- No LLM generation of context.
- No replacement of `PromptOverrides` — both coexist; the screen labels
  one "replaces the shipped prompt" and the other "adds facts to it", and
  060's agent screen links both.

## Verificação de constituição

- **II** — the token budget is a named constant, enforced at validation.
- **IV** — the screening gate; and the context is *configuration*, so it
  reaches the model via the prompt like any prompt text — masking of
  identifiers still applies on the way out (Article IV.5's existing path).
- **VI** — assembly is provider-neutral text; no role gains a
  vendor-specific shape.
- **VII** — the mechanism ships with an ablation switch (context on/off)
  and a synthetic scenario where the LXC fact changes the conclusion's
  source citation; contribution reported as a number.
- **VIII/XI** — one schema section (tier 3), constants (tier 4), screen
  (console); no new storage — the config tree carries it.
- **XII** — schema validation tests first; the assembly test drives a
  scripted model client; scenario delta reported.

## Raio de impacto

`AgentsConfig` (4 callers: bindings, schema exports, root) — additive field,
merge behaviour covered by the config-service suite; `prompt_for` callers
(run composition); the catalogue route (new section appears — 058's editor
picks it up from the catalogue, which is most of the screen for free);
`schema.ts` regeneration.
