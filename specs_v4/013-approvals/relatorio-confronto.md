# 013 Approvals — implementation confrontation

Date: 2026-08-13

## Conclusion

The control file was stale. Its three entries said NOT STARTED, but the code
already contained a complete accessibility fix and part of the two-inbox fix.
The empty-state rule was present too, but it read a legacy configuration shape
and could miss the live service's canonical value and default.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Two nearly synonymous inboxes | NOT STARTED | PARTIAL. Both screens already linked to the other queue, but the approvals queue was still named Approvals and the explanatory copy was insufficient. See console/src/surfaces/screens/approvals.tsx and console/src/surfaces/screens/proposals.tsx. | DONE |
| 2. Empty state does not cite the active rule | NOT STARTED | PARTIAL and incorrect for the live API. The existing code read approval.required_above from the effective response. The real schema is policies.approvals.threshold, and the effective fields endpoint is what exposes value, default, and provenance together. | DONE |
| 3. Duplicate accessibility CTA | NOT STARTED | DONE before this audit. EmptyStateAction already separated link and button actions, and EmptyState rendered one anchor for a navigation action. This was introduced by commit fb80663 and covered by the component tests. | DONE |

The structural merge into a Decisions inbox from spec 090 remains intentionally
out of scope. This change implements the minimum correction without changing
routes.

## Evidence and corrections

### 1. Inbox identity

The specification requires that a reader can distinguish:

- an action the agent wants to take now; and
- a proposed deployment change that should persist into the future.

The existing mutual links were real, so the control's NOT STARTED status was
false. They did not fully satisfy the acceptance criterion because the visible
name and context still left the distinction implicit.

The correction:

- renames the navigation and page title from Approvals to Actions awaiting
  approval in English, and to Ações aguardando aprovação in Brazilian
  Portuguese;
- describes the approvals queue as actions the agent wants to take now;
- adds an explicit sentence on each screen explaining the purpose of the other
  inbox;
- keeps /approvals and /proposals unchanged.

The implementation is at console/src/i18n/en.ts:28, console/src/i18n/en.ts:76,
console/src/i18n/en.ts:652, console/src/i18n/en.ts:1300, and the corresponding
Brazilian Portuguese entries. The two cross-inbox lines are at
console/src/surfaces/screens/approvals.tsx:293-300 and
console/src/surfaces/screens/proposals.tsx:114-121.

### 2. Active approval rule

The backend is the source of truth:

- platform/config_service/schema/policies.py:258-278 declares
  policies.approvals.threshold and gives it the shipped default
  write_reversible;
- gateway/http/routes/config.py:547-597 serves every field with value, default,
  and provenance;
- gateway/http/routes/config.py:440-452 serves the effective values map, but
  that map does not provide the same reliable default metadata.

Before this audit, the approvals screen only looked for the legacy flat
approval.required_above key in the effective response. That meant the empty
state could silently omit the active rule on a deployment using the canonical
schema, especially when the value came from the shipped default.

The correction in console/src/surfaces/screens/approvals.tsx:71-117 and
console/src/surfaces/screens/approvals.tsx:176-206 now:

1. reads /v1/config/{node_id}/fields;
2. prefers policies.approvals.threshold;
3. displays the effective value, or the schema default when value is absent;
4. displays whether the value comes from a node or from the deployment default;
5. retains a localized fallback for the legacy mockplane fixtures while they
   still expose approval.required_above;
6. continues to prioritize the unfinished-setup explanation when setup is not
   complete.

The example read_sensitive from the specification is not hardcoded. The screen
renders the deployment's actual threshold. The current backend default is
write_reversible, so that is what the default case correctly reports.

### 3. Accessibility CTA

This point was already implemented before the audit. The union in
console/src/components/state.tsx:23-34 makes a navigation action a link and a
handler action a button; console/src/components/state.tsx:72-94 renders only
the matching element. The existing component tests cover both forms.

An approvals-specific regression test was added at
console/tests/unit/surfaces/approvals.test.tsx:185-199 to assert that See what
is running has exactly one link role and no button role.

## Verification

Passed:

- Focused console regression suite: 4 files, 56 tests passed. It covers both
  inboxes, canonical configured threshold, canonical default threshold, legacy
  fixture compatibility, the unfinished-setup branch, and the single CTA.
- Backend schema and config-route tests: 48 passed.
- ESLint on the changed console files.
- Prettier check on the changed console files.

The repository-wide console gates are currently blocked by unrelated dirty
worktree changes:

- typecheck: console/tests/unit/surfaces/rows.test.tsx:144 uses an unknown
  title property; console/tests/unit/surfaces/run-trigger.test.ts:3 imports the
  missing @/surfaces/run-trigger module;
- lint: console/tests/unit/surfaces/run-trigger.test.ts:13,22,26 reports unsafe
  calls, and console/tests/unit/surfaces/runs.test.tsx:66 reports an
  unnecessary optional chain.

Those files were not changed because they are outside this specification and
were already modified or untracked in the worktree.

## Control reconciliation

The control file was updated to mark all three items DONE and to link this
report. The status reflects verified behavior, not the previous checklist
labels.
