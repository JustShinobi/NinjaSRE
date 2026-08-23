# Plano — 060 The agent, visible and tunable

## O que existe, verified — this feature models nothing new

The spec's own correction holds against the code:

- **Topology is configuration**: `AgentsConfig`
  (`platform/config_service/schema/agents.py:86`) carries
  `subagents: tuple[SubAgentConfig, ...]` (name, description,
  system_prompt, capabilities, max_iterations, model_role, enabled —
  distinct names enforced), `prompts: PromptOverrides`, and the four
  budgets, each `Annotated[..., Field(ge=…, le=<constant>)]` — **bounded
  above by the constants**, so a team can lower and never raise
  (Article II.6 made schema).
- **Models are roles**: `ModelsConfig.for_role` /
  `selection_for` over the eight roles — `selection_for` returning `None`
  for a fall-through is precisely what lets a screen distinguish "chosen"
  from "defaulted", which the provenance column needs.
- **Tools**: `GET /v1/capabilities`; `capabilities/tools/` split
  `system/` vs `remediation/`; each capability's metadata carries
  `side_effect_level` and its required integration; the catalogue screen
  (050-fixed) already joins capability → blocking integration ("why did it
  not try that").
- **MCP**: `capabilities/protocols/catalogue.py` — `BridgedCapability`
  with `qualified_name`, `unavailable` servers reported,
  `executable_tools` gated on operator classification. Origin is already
  a fact on the capability.
- **Autonomy reading**: `/v1/autonomy/policy/{node_id}/explain` and
  `preview` (`platform/autonomy/preview.py` — per-action before/after with
  `describe()` sentences) exist and are unsurfaced; 058 builds the editor,
  this feature builds the *reading*.
- **Guardian**: `GET /v1/config/{node_id}/guardian`, read-only by 058's
  decision.

The feature is one screen (three tabs, D3 §4) plus the editor wiring into
058's pattern.

## Escopo A — "what it is": the topology tab

- A hierarchical rendering: orchestrator → sub-orchestrators → specialists,
  from `AgentsConfig.subagents` + the pipeline's fixed stages (which
  stages exist is architecture, not config — the spec's out-of-scope; the
  stage list is read from a declared structure, not editable).
- State on the node (enabled, entry point); click opens the editor —
  058's catalogue-driven pattern over the `agents` section (`subagents` is
  part of the config document, so the write path, preview, provenance and
  audit all come from 058 for free).
- A structured-text view beside the visual one: the config document
  section as the operator would edit it, both views over one source.
- Templates for common topologies as **starting documents** (like 059's
  template: server-derived data, applied through the ordinary
  preview-then-save flow).
- **No per-stage model identifier** (D3 §4's fixed decision, Article VI):
  the screen shows the *role*; the resolved provider/model appears as a
  configuration value with provenance — `selection_for`'s None means the
  row says "deployment default", never a vendor name presented as fixed.

## Escopo B — "what it can do": the tools tab

Grouped by the one distinction that changes risk: **reads** vs **writes**
(`system/` vs `remediation/`, surfaced as the visual organisation, plus
`side_effect_level` as the per-row badge — colour and label, never colour
alone, D1 rule 2). Per tool: description, required integration, configured
state; an unconfigured tool renders dimmed **with the reason** — the same
join the catalogue screen computes, reused not recomputed (this tab and
`/catalogue` share the data function; the difference is organisation).
MCP-bridged tools carry their server as origin, `unavailable` servers
listed with their report, unclassified bridged tools shown as
not-executable with the classification pointer.

## Escopo C — "what it will do alone": the autonomy tab

The reading the spec asks for: one sentence per action class under the
current policy — built from `explain` over a fixed representative action
set (one per capability risk class, a declared constant list), rendered as
"would be proposed / would execute / would be refused by <bound>". The
`Resolution.describe()` sentences are the material; the tab adds the
per-class iteration. Dry-run state banners here as everywhere (058). The
kill switch is *not* on this screen — it is 058's shell control; this tab
links the policy editor.

## Decisions the spec left open

1. **The screen is one area** (`/agent`, settings zone, D2) with three
   tabs, not three areas — the three questions are one subject, and the
   nav already grew in 052.
2. **The graph rendering reuses `console/src/surfaces/graph.tsx`**
   (topology screen's machinery) rather than a new renderer; if it cannot
   express hierarchy cleanly, extend it — a second graph component is a
   second visual language for the same concept.
3. **The representative action set is data, not sampled history** — a new
   deployment has no history, and the tab must answer on day one; 058's
   `preview` over recorded actions complements it once history exists
   (both shown when both are available).

## O que esta feature NÃO faz

- No pipeline-definition editing, no tool registration UI, no prompt
  playground (spec's out-of-scope).
- No policy editing (058), no context editing (059) — linked, not
  duplicated.
- No new backend concept; the only route work is (a) exposing the pipeline
  stage declaration read-only if no route carries it today, and (b) the
  representative-action explain iteration, which is a thin composition
  over the existing explain route.

## Verificação de constituição

- **VI** — the no-vendor-per-stage rule is this screen's defining
  decision; a test asserts no provider identifier renders outside the
  provenance-attributed model-role rows.
- **II** — budget fields render their ceilings from the constants; the
  editor cannot offer more than the schema allows (structural, from 058's
  catalogue-driven controls).
- **III** — the autonomy tab is read-only rendering of the policy's own
  answers; nothing here changes what executes.
- **VIII** — console over HTTP; the explain composition lives in the
  gateway route layer over `platform/autonomy`.
- **XII** — component tests per tab; the vendor-identifier absence test;
  e2e answering the spec's closing question ("what will this thing do
  alone") from the rendered page.
