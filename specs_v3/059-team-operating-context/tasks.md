# Tarefas — 059 Team operating context

Depends on 058 (editor pattern, clear-to-inherit semantics, config write
path). Template derivation reads 053/054 output but degrades to prompts-only
without them. Ordered, one commit each, test-first.

## Fase 1 — the schema section

- **T-001** Failing tests: `OperatingContext` with named sections; distinct
  names enforced; inheritance through the tree — child adds a section,
  overrides one by name, removes one via the clear-to-inherit marker;
  provenance reported per section. Implement in
  `platform/config_service/schema/agents.py`.
- **T-002** Failing tests: the token budget — a document over
  `OPERATING_CONTEXT_TOKEN_BUDGET` is refused at validation naming the
  overage; the estimator is the budget policy's. Constant in
  `config/constants/agents.py`. Implement.
- **T-003** Failing tests: a section body carrying a credential-shaped
  value is refused naming rule and location, value unlogged (acceptance 4).
  Implement the screening in validation.

## Fase 2 — assembly

- **T-004** Failing test (acceptance 1): a run composed with an override
  *and* operating context sends the model one system prompt containing
  both — the shipped/overridden prompt first, the rendered sections after,
  asserted through a scripted `core.llm` client. A run with neither is
  byte-identical to today (the no-configuration deployment pays nothing).
  Implement the append at the prompt-assembly site; included roles as a
  named constant.
- **T-005** Failing test: intake/diagnose do not receive the context by
  default. Implement.
- **T-006** Synthetic scenario + ablation: the LXC-metrics fact in context
  changes which source the pressure claim cites; context-off run shows the
  difference. Report the scenario-suite delta and the ablation number.

## Fase 3 — the template

- **T-007** Failing tests: with an empty section list, the derived
  template carries the fixture estate's zones/CIDRs, the signal-map
  sources, the LXC fact, and human-only placeholder prompts; with no
  estate, it degrades to the placeholder skeleton and says why. The
  builder imports nothing from `core.llm` (structural test). Implement
  server-side (template rides the context read route).

## Fase 4 — the screen

- **T-008** Component tests first: sections editable per node with 058's
  pattern; per-section provenance; budget meter; the preview renders the
  exact final prompt text before save (acceptance 6); UI copy states
  fact-vs-instruction with the runbook/policy links. Implement.
- **T-009** e2e: fill a section from the template, save at the org node,
  override one section at a team node, and see provenance distinguish the
  two (acceptance 2).
- **T-010** `make verify` green; `schema.ts` regenerated; visual baseline
  for the new screen.

## Definição de pronto

1. Both the distributed prompt and the operating context provably reach
   the model in one run (T-004).
2. Sections inherit with provenance like any config value (T-001, T-009).
3. Over-budget context is refused naming the excess (T-002).
4. Credential-shaped content is refused, value nowhere (T-003).
5. The initial template arrives pre-filled with discovered zones and
   signal sources (T-007).
6. The screen shows the final model-bound text before save (T-008).

## Dependências em outras features specs_v3

- **058** (hard): editor pattern, removal marker, write/audit path.
- **053/054** (soft): template derivation content; degrades without them.
- **Feeds 060** (the agent screen links context beside overrides and shows
  the same assembly), **061** (context proposals target this section —
  the proposal's "what would change" preview is this feature's final-text
  rendering).
