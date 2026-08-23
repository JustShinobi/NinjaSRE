# Tarefas — 058 Configuração, após primeira execução

Depends on 050 (node resolution on `/autonomy` and `/catalogue`) and 051
(permission-row pattern; credential state display). Ordered, one commit
each, test-first.

## Phase 1 — gateway extensions

- **T-001** Failing tests in the config service: the preview response
  carries `redundant` — paths whose patched value equals the inherited
  effective value, each naming the level it inherits from. Implement beside
  the existing preview calculation.
- **T-002** Failing tests: the patch shape expresses removal
  (clear-to-inherit); preview of a removal shows "reverts to inherited
  <value> from <level>"; applying it deletes the node-local value.
  Implement.

## Phase 2 — the editor pattern

- **T-003** Component tests first: the catalogue-driven field editor —
  typed controls from catalogue entries, patch accumulation, preview
  invalidated by any later edit, save absent until a current preview
  exists, server's `redundant`/`locked`/`gated` markings rendered in the
  diff. Extend `ConfigPreview` into the editing panel.
- **T-004** Save path: console proxy route for `PUT /v1/config/{node_id}`;
  failing test that a save lands in the audit trail with actor and the
  changed paths. e2e: edit → preview → save → provenance column shows the
  new level; and the bypass attempt (save without preview) is impossible.
- **T-005** Clear-to-inherit control per locally-set field, using T-002;
  component test distinguishes it from set-equal-to-parent.

## Phase 3 — autonomy

- **T-006** Component tests first: policy editor over
  `PUT /v1/autonomy/policy/{node_id}` with `explain` + `preview` rendered
  above the save control; the newly-autonomous list is present before save
  is enabled. Implement.
- **T-007** Dry-run toggle with persistent banner; component test for both
  states; the banner uses a state colour, never the accent (design-token
  test covers).
- **T-008** Kill switch in the shell topbar: engage/release over the
  routes; confirmation names the consequence; engaged state banners on
  every screen for every viewer; engage control present only with
  `config.write`. e2e from two different screens.
- **T-009** Overrides list with duration and reason in-row (component
  test).

## Phase 4 — administration

- **T-010** SSO form: `test` must succeed on the currently saved document
  before `activate` enables; any edit invalidates the test result.
  Component tests + e2e (acceptance 4).
- **T-011** Token issuance with show-once secret (rendered from the
  issuance response only; a re-render or refetch shows metadata, never the
  secret — asserted), listing, revocation with consequence-naming
  confirmation (acceptance 5).
- **T-012** Grants add/remove; the last-owner refusal renders its specific
  message (failing test drives the gateway's refusal through the screen).

## Phase 5 — detectors and schedules

- **T-013** Detector enable/disable with dry-run in the enable flow;
  dry-run rendering shared with 056's candidates. Component tests first.
- **T-014** Schedule CRUD with destructive-action treatment. Component
  tests first.

## Phase 6 — gate

- **T-015** Route-permission rows for any new console proxy endpoints;
  `make verify` green; visual baselines re-captured for the four changed
  screens; regenerate `schema.ts` for the preview-response change.

## Definition of done

1. Changing a value requires seeing the preview, and the preview shows
   per-value provenance (T-003/T-004 e2e).
2. Setting a value identical to the inherited one warns explicitly, from
   the server's `redundant` list (T-001/T-003).
3. The autonomy policy is editable with `explain` before save; the kill
   switch is reachable from any screen (T-006/T-008).
4. SSO cannot activate without a passing test on the same document
   (T-010).
5. A token secret appears once and is not recoverable afterwards (T-011).
6. Every new write appears in the audit with actor, resource, and outcome
   (asserted in T-004/T-008/T-010/T-011/T-012 individually).

## Dependencies on other specs_v3 features

- **050** (hard): node resolution; **051** (hard): permission patterns,
  credential state rows.
- **Feeds 059** (the editor pattern and the config-tree write path are
  what operational context rides), **060** (autonomy explain/preview
  rendering; agent config editing), **061** (the preview-before-approve
  discipline and approval-gated save path), **062** (machine-token
  issuance UI for ingress).
