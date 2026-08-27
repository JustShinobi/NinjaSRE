# Tarefas — 060 The agent, visible and tunable

Depends on 058 (editor pattern, autonomy explain surfaced, node
resolution) and 050 (catalogue screen fixed — this feature shares its
data join). Ordered, one commit each, test-first.

## Fase 1 — the data the tabs need

- **T-001** Failing contract test: a read-only route serves the pipeline
  stage declaration (names, order, what each consults) if none does
  today; otherwise pin the existing shape. Implement minimally.
- **T-002** Failing contract test: the representative-action explain — a
  declared action set (one per risk class, a constants-tier list) resolved
  through `platform/autonomy` explain, served as one document of
  per-class sentences. Implement as a thin gateway composition.
- **T-003** Extract the capability↔integration join the catalogue screen
  computes into a shared console data function; failing test that both
  call sites produce identical rows.

## Fase 2 — the screen

- **T-004** New `/agent` area in `AREAS` (settings zone); i18n rows; the
  050 smoke walk and shell suites pick it up by enumeration. Component
  test for the three-tab shell.
- **T-005** Topology tab: hierarchical rendering from
  `AgentsConfig.subagents` + the stage declaration; enabled state on the
  node; structured-text view beside it over the same document. Component
  tests first, including the two-views-one-source assertion.
- **T-006** Topology editing: click-through to 058's catalogue-driven
  editor for the `agents` section; budgets render their schema ceilings;
  a topology template applied through preview-then-save. e2e: disable a
  subagent, see provenance, re-enable.
- **T-007** Failing test (Article VI): no provider identifier renders
  anywhere on the screen except in model-role rows that carry provenance;
  an unset role renders "deployment default". Implement the model-role
  panel.
- **T-008** Tools tab: read/write grouping with `side_effect_level`
  badges (colour + label), unconfigured tools dimmed with the named
  missing integration, MCP tools with server origin and unavailable-server
  reports, unclassified bridged tools marked not-executable. Component
  tests first.
- **T-009** Autonomy tab: per-class sentences from T-002; dry-run banner;
  link (not embed) to 058's policy editor; when action history exists,
  058's recorded-action preview shown beside the representative set.
  Component tests first.

## Fase 3 — proof

- **T-010** e2e: on the seeded deployment, answer the three questions
  from the rendered pages alone — which stages run and which specialists
  are enabled; which tools exist, split by risk, with blockers named;
  what each action class would do under the current policy — with no YAML
  shown outside the structured-text view (acceptance 5).
- **T-011** `make verify` green; visual baselines for the new screen;
  `schema.ts` regenerated for T-001/T-002.

## Definição de pronto

1. The investigation's stages and their enablement render without any
   fixed vendor model identifier (T-005/T-007).
2. Tools are visibly split read vs write; every tool with a missing
   integration is marked with the integration named (T-008).
3. MCP-origin tools are identifiable as such (T-008).
4. The autonomy tab states, in sentences, what each action class would do
   under the current policy, via explain/preview (T-002/T-009).
5. An operator answers "what will this do alone" from the console alone
   (T-010).

## Dependências em outras features specs_v3

- **058** (hard): editor, autonomy surfacing; **050** (hard): the
  catalogue data join this screen shares.
- **059** (soft): the context section appears beside prompt overrides in
  the topology tab's editor links, labelled adds-vs-replaces.
- **Feeds 061**: the "what it would do" reading is the material an
  operator uses to judge proposals about detectors and autonomy.
