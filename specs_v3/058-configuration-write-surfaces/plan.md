# Plano — 058 Configuração, após primeira execução

## What exists, verified

The spec's premise — "the backend already solved the hard part" — checks out:

- **Config**: `GET /v1/config/{node_id}` with provenance (rendered by
  `configuration.tsx`), `GET /v1/config/{node_id}/catalogue` (type, range,
  default, description — the route 050 fixed the screen for),
  `PUT /v1/config/{node_id}`, `POST /v1/config/{node_id}/preview`. The
  console's `ConfigPreview` (`console/src/surfaces/preview.tsx`) already
  posts a patch to `/api/preview` and renders **the server's answer only**
  ("the preview MUST be the server's answer, never a client-side merge"),
  including locked fields, approval-gated fields, and "Nothing would
  change". It is behind `config.write` today and lacks only a real editor
  feeding it patches and a save path.
- **Autonomy**: the full family — `PUT /v1/autonomy/policy/{node_id}`,
  `/bounds`, `/dry-run`, `/explain`, `/overrides`, `/preview`
  (`platform/autonomy/preview.py::preview_change` — replays recorded
  actions under both policies, "reassuring and wrong" is designed out), and
  `POST|DELETE /v1/autonomy/kill-switch`. No surface calls any of the
  writes.
- **Identity**: `GET|PUT /identity/sso`, `/sso/test`, `/sso/activate`;
  `POST /identity/tokens`, `/tokens/revoke`, `DELETE /identity/tokens/{id}`
  (`platform/identity/tokens.py` — revocation drops the cache before
  returning; the store holds a hash, so show-once is structural);
  `POST|DELETE /identity/grants`. The show-once pattern is established by
  `DurableCredentialView` (`gateway/http/routes/first_run.py:79`).
- **Detectors/schedules**: enable/disable/dry-run and full CRUD routes;
  both screens read-only.

This feature is therefore almost entirely console work plus two small
gateway extensions (redundant-value detection, clear-to-inherit).

## Scope A — the configuration editor

Field-level editing on `/configuration`, driven by the node's catalogue:

- Each catalogue entry renders a typed control (type/range/default from the
  catalogue — the console holds no field table of its own, same doctrine as
  the generated client).
- **Preview is mandatory by construction**: the save action does not exist
  until a preview of the *current* patch has been rendered; editing any
  field after a preview invalidates it. This is a client-flow guarantee —
  the API cannot know a human saw the diff — and the e2e test drives the
  bypass attempt.
- **The redundant-set warning is the server's**: the preview response gains
  a `redundant` list — paths whose patched value equals what the node
  already inherits. Computed in the config service beside the existing
  preview calculation (it has both documents in hand), so the CLI's
  `diff_config` can say the same thing. Rendered inside the diff
  (acceptance 2).
- **Clear-to-inherit is first-class**: a distinct control per
  locally-set field ("remove this override"), carried in the patch as an
  explicit removal marker, distinct from setting the inherited value. If
  the config service's patch shape cannot express removal today, adding it
  is in scope, with the preview showing "reverts to inherited <value> from
  <level>".
- Writes go through the console's established proxy pattern
  (`app/api/preview` sibling for the save), and every save lands in the
  audit trail with actor and diff summary (acceptance 6 — the config
  service's write path already audits; the test asserts it).

## Scope B — autonomy

A real editor on `/autonomy` (which 050 made resolve its node):

- policy read/write with **`explain` and `preview` shown before save** —
  `preview_change.to_record()` already produces the summary sentence and
  the newly-autonomous list, which is the half an operator must read; the
  save control sits below that list, not beside the form;
- dry-run toggle with a persistent, visually distinct banner state (D1:
  state colour, never the accent) — it is the propose/act boundary;
- **the kill switch in the shell, not the screen**: a control in the topbar
  (beside 052's investigate action), visible on every screen, engaging
  `POST /v1/autonomy/kill-switch` with D2's irreversible-action treatment —
  the confirmation names what stops ("every automated write, immediately"),
  and the engaged state is a shell-level banner until released;
- overrides listed with duration and reason visible in the row.

## Scope C — administration

- **SSO**: form over `GET|PUT /identity/sso`; `activate` is disabled until
  a `test` succeeded *for the currently saved document* — a test result is
  invalidated by any edit, the lockout-prevention the routes were built for.
- **Machine tokens**: issue (show-once secret, rendered exactly once and
  never re-fetchable — structural, the store holds a hash), list, revoke
  with D2's consequence-naming confirmation ("clients using this token stop
  authenticating now").
- **Grants**: add/remove role bindings; the last-owner removal refusal is
  rendered as its own message, not a generic failure — the gateway already
  refuses; the console maps that specific error.

## Scope D — detectors and schedules

- Detectors: enable/disable with dry-run offered *in the enable flow* —
  "what this would have fired on" before it fires (the D2 consequent-action
  tier), reusing the dry-run rendering 056's candidates need.
- Schedules: create/edit/delete over the existing CRUD, with the D2
  destructive-action levels applied (delete names what stops running).

## What stays read-only, and why (restated from the spec as scope)

Credentials appear as state only (051 owns the write path; no value, no
masked value). Guardrails (`GET /v1/config/{node_id}/guardian`) stay
read-only with the file path shown — a UI edit is a deployment
de-protecting itself through a typo.

## Decisions the spec left open

1. **One editor pattern, reused**: catalogue-driven field controls +
   server-answer preview + save-after-preview is built once (extending
   `ConfigPreview` into an editing panel) and reused by autonomy (policy
   document), 059 (context sections) and 060 (agent config) — recorded here
   because 059/060 plan against it.
2. **Approval-gated fields**: the preview already reports
   `requires_approval`; the editor renders "will be queued" (the component
   docstring's wording) and the save produces the approval rather than the
   change. No new mechanism.
3. **Kill-switch permission**: engaging requires `config.write`; the
   *banner* is visible to every viewer — everyone should know automation
   is stopped, only governors may stop it.

## Constitution check

- **III** — approval-gated config paths keep their gate; the kill switch
  is the Article III.5 revocation control given a surface.
- **IV** — no credential value ever rendered (state-only rows); token
  secrets shown once from the issuance response only.
- **VIII** — console speaks HTTP; the two gateway extensions live in the
  config service beside their existing calculations.
- **XII** — component tests per editor, e2e for the preview-before-save
  and test-before-activate flows; the redundant-list and removal-marker
  changes land test-first in the config service suites.
- **I/II/V/VI/VII/IX/X/XI/XIII** — unaffected or trivially held (audit on
  every write; constants for any new bound; English).
