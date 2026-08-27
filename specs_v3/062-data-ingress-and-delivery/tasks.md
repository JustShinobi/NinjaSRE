# Tarefas — 062 Ingress and delivery

Depends on 051 (token issuance surface pattern), 058 (config-tree editor
and simulation discipline), 055 (resolution, ingress panel to absorb).
Ordered, one commit each, test-first.

## Fase 1 — the transit ledger

- **T-001** Failing contract tests for the new repository port (fake +
  postgres): record ingress delivery with outcome/reason/matched
  route/resolved resource; one masked sample per source, replaced on the
  next delivery; page-size bounds; retention as a `DataClass` swept by
  the one sweeper. Implement port, fake, migration, postgres repository.
  Update every port-count assertion and document in the same commit.
- **T-002** Failing tests: the webhook handler writes the ledger on every
  path — accepted, rejected (with reason), shed, duplicate; the sample is
  stored only after masking, and a sentinel in the raw payload is absent
  from the stored sample. Implement.
- **T-003** Failing contract tests: ingress read routes — per-source
  status (last delivery, counts per window, never-delivered flag), recent
  rejections, the masked sample. Implement + route-permission rows.

## Fase 2 — routing rules

- **T-004** Characterisation test of today's post-verification behaviour
  (verified delivery → matched team → investigation). Green before the
  seam moves.
- **T-005** Failing tests for the rules section (058's tree): ordered
  rules; matchers by source/zone/criticality/resource resolved from the
  estate; validation refuses a rule set without an explicit catch-all
  last rule; discard requires a reason. Implement the schema section.
- **T-006** Failing tests for evaluation in `platform/`: first match
  wins; the default rule set reproduces T-004 exactly; discarded
  deliveries still ledger. Move the seam; T-004 stays green.
- **T-007** Failing contract test: the simulate endpoint takes a payload
  or a ledger delivery id and returns rule/team/action from the same
  evaluation function (asserted by construction — one function, two
  callers). Implement.

## Fase 3 — outbound

- **T-008** Failing tests: destination model — closed event enum,
  channel binding to a catalogue integration, detail level; defaults
  deny raw evidence; the outbound body passes masking and the applied
  policy is named in the destination record. Implement.
- **T-009** Failing tests: dispatch on each event type; attempts
  ledgered; bounded retry with named constants; manual re-send route,
  audited. Implement.
- **T-010** Failing test: a deployment with no delivery-capable
  integration shows destinations unconfigurable with the reason.

## Fase 4 — the Dados screen

- **T-011** Nav item "Dados" (settings zone, D2); three-column transit
  layout (D3 §5): ingress with never-delivered as the most prominent
  state, rules in order with the catch-all always visible, destinations
  with event/channel/detail and masking policy. Component tests first;
  055's ingress panel absorbed here.
- **T-012** Simulation in the rule editor: paste a payload or pick a
  recent delivery, see rule/team/action before save; save disabled until
  simulated (the 058 flow guarantee). e2e including the bypass attempt.
- **T-013** Provenance drawer: from an ingress row to rule, team, and
  run; from a finding to its query/origin/instant via the trace link.
  Component tests.
- **T-014** Failed delivery visible with reason and re-send control
  (acceptance 6). e2e.

## Fase 5 — gate

- **T-015** `make verify` + `make test-postgres` green; `schema.ts`
  regenerated; visual baselines for the new screen; the 050 smoke walk
  picks up `/data` by enumeration.

## Definição de pronto

1. Each ingress route shows URL, token state, format, and last delivery
   with date, outcome, and masked sample (T-003/T-011).
2. A configured source that never delivered is visibly flagged without
   the operator hunting (T-003/T-011).
3. A routing rule is simulated against a real payload before save,
   showing rule, team, and action (T-007/T-012).
4. The fate of unmatched deliveries is an explicit, always-visible choice
   (T-005/T-011).
5. A destination declares events, channel, and detail level, and shows
   its masking policy (T-008/T-011).
6. A failed delivery shows its reason and can be re-sent (T-009/T-014).
7. Given a finding, the interface answers which query, origin, and
   instant it came from (T-013).

## Dependências em outras features specs_v3

- **051** (hard), **058** (hard), **055** (hard — absorbs its panel and
  builds on its resolution). **053** supplies zone/criticality matchers;
  **061** supplies the approval-pending event type (the enum ships with
  it; dispatch activates when 061 lands).
