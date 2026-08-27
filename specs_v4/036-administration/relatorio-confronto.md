# 036 Administration — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` understated this spec's own state in the same direction this
series keeps finding. It marked item 1 `PARCIAL` ("separar sessões de machine
tokens, headers de coluna e a investigação de por que cada page-load emite
token: pendentes") and items 2 through 5 `NÃO INICIADO`, with no detail at
all. Reading `console/src/surfaces/screens/administration.tsx`,
`console/src/surfaces/tokens.tsx`, `console/src/surfaces/sso.tsx` and
`console/src/surfaces/grants.tsx` before touching anything, then running their
existing test suites rather than trusting the reading, found that a chain of
prior commits already at `HEAD` (`3286a64` "issue a machine token, see it once,
and revoke it knowing what stops"; `2780b68` "configure single sign-on, and
refuse to activate one nobody tested"; `689b9c4` "serve the role catalogue, so
the grant form offers what the deployment has"; `6b00e4a` "grant and remove an
identity role from the console"; `bbd74a0` "stop nav prefetch stampede, group
catalogue and revoked tokens"; `1ef8dd6`; `c512fae`) had already built almost
everything `spec.md`'s five items ask for, none of it reflected in
`controle.md`. Items 1, 2 and 5 were, on inspection and on running their own
tests, **already fully done**: sessions and machine tokens are already two
separate, separately-tested components (`SessionPanel`/`TokenPanel`,
`token-identity.ts`'s `isConsoleSession`); the "why does every page-load seem
to issue a token" question item 1 asks to investigate was already investigated
and fixed, by `bbd74a0` disabling the sidebar's default `<Link prefetch>`,
whose own comment names the mechanism directly ("a stampede the gateway's
session handling was not built to absorb"); the SSO form's `problems` list
starts empty and is filled only by an actual save or test, never on load; and
a newly-issued token's fixed scope is already named on the form
(`token-issued-scopes`), matching what the backend's `_scoped()` genuinely
grants an unscoped token. Running `tokens.test.tsx`, `sso.test.tsx` and
`grants.test.tsx` against the unmodified tree confirmed 76 tests already
covering this, all green, before this confrontation changed anything.

Items 3 and 4 were each half right and half wrong in the same row, which is
exactly the shape `controle.md`'s bare `NÃO INICIADO` could not have
distinguished. Item 3's role-description half was already built — the grant
form's role `<Select>` already shows, at the point of choice, a live
description composed from `/identity/roles`' own permission list, deliberately
not a hand-written sentence, for the same reason the route's own docstring
gives about the role list itself ("a second copy of the catalogue... is the
copy that is wrong on the day somebody adds a permission"); `grants.test.tsx`
already pinned this and it passed unmodified. But the *grant list itself* —
the rows above that select — still rendered the raw `principal_id` in
`font-mono`, unresolved to a name: `bootstrap-administrator` and
`local-admin`, the exact two strings `spec.md`'s own text quotes as examples,
are genuinely what a reader saw and still would have seen. That is fixed here,
test-first. Item 4's "Not recorded" had already been replaced by a prior,
uncredited pass — but with the principal's raw `user_id`, not with a sentence
saying what the record is; an improvement over "Not recorded" reading as a
bug, but still a slug rather than the "conta de serviço criada no deploy, sem
e-mail" `spec.md` asks for. That is fixed here too, test-first, with the
sentence in both locales.

I looked specifically, as instructed, for the shape 035's confrontation just
found — a lookup table declared, documented as the thing that turns
identifiers into words, and shipped empty — across every file this screen
reads and renders (`administration.tsx`, `grants.tsx`, `tokens.tsx`,
`sso.tsx`, `token-identity.ts`, and `platform/identity/`'s own permission and
account modules). None exists here: `roleDescriptions` is built from a live
read rather than a static table, and no other declared-but-unpopulated map
was found. This screen's own version of that defect shape was smaller and
different — a fallback that degraded to a raw identifier instead of falling
through to nothing — and both instances of it are fixed below.

While reading the permission story for the write I was told to check in both
directions — a control the backend would allow but the console hides, or the
reverse — I traced all four of this screen's own permission checks
(`token.manage`, `sso.manage`, `identity.write`, and the area-level
`identity.read` that gates reaching `/administration` at all) against
`gateway/http/security/route_permissions.py`'s `_IDENTITY_ROUTES` and found
them exact matches in both directions, confirmed by the passing
`tests/contract/console/test_console_shell.py` inside the run recorded below.

**Correction made after coordinator review.** The first pass of this
confrontation traced the mock data plane's `kind` vocabulary
(`"person"`/`"machine"`) against the real `PrincipalKind` enum
(`platform/persistence/ports/identity_repository.py:26-30`, which declares
exactly `"user"` and `"service_account"`), named the two as diverging, and
left the divergence to `tools/mockplane`'s own surface on the reasoning that
fixing it would mean regenerating every scenario's principal data — true, but
beside the point that the divergence sits directly underneath item 4's own
fix. `principalIdentity`'s branch keys on `kind === 'service_account'`
exactly, so a mock that never serves that value never exercises the branch on
anything the fixture-driven suites — or an operator looking at the
demonstration deployment the mock plane serves — actually see; only this
confrontation's own direct unit test did. That is not cosmetic: it means the
fix built for item 4 was verified in isolation but not where the fixture data
would otherwise have proven it. Corrected here: `tools/mockplane/dataset/served.py`'s
`USERS` and `identity_records()`, and `tools/mockplane/dataset/build.py`'s
`empty_records()`, now serve the two values the backend actually declares,
read off one source (`USERS[n]["kind"]`) rather than repeated as a second
literal that could drift again; every committed scenario was rebuilt with
`uv run python -m tools.mockplane build`; and a new contract test,
`test_every_principal_kind_is_one_the_backend_actually_declares`
(`tests/contract/fixtures/test_dataset_contract.py:100-124`), pins the
invariant directly against the live `PrincipalKind` enum rather than against
a value somebody has to remember is still correct — schema validation alone
would never have caught this, because the wire type is a plain `str`. Both
the console's own source and the mock plane's own runtime code were checked,
specifically, for anything that branches on the literal strings
`'person'`/`'machine'` before the vocabulary changed; neither does (detailed
under item 4 below), so no second half of this fix was needed anywhere else.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Lista de tokens é um despejo | PARCIAL (`bbd74a0`) — "separar sessões de machine tokens, headers de coluna e a investigação... pendentes" | Wrong on all three sub-points. Sessions and machine tokens were already two components, already grouped by principal with "end all sessions"; both panels already carried column headers (`token-columns`, `session-columns`); revoked tokens already collapsed behind a `{count} revoked` disclosure. The token-emission question was already investigated and fixed by `bbd74a0` (disabled `<Link prefetch>`). 76 existing tests in `tokens.test.tsx` already pinned this and all passed unmodified. | DONE (no change) |
| 2. SSO grita erros antes de qualquer input | NÃO INICIADO | Wrong — already done. `SsoForm`'s `problems` state starts from the `[]` `administration.tsx` hands it and changes only through `save()`/`test()`/`activate()`'s own `adopt()`; the screen's own comment documents the exact bug ("the deployment always answers with 'issuer is required' and seven siblings for a form nobody has touched yet") as the reason. `sso.test.tsx`'s 21 tests already passed unmodified. | DONE (no change) |
| 3. Grants e roles em slug | NÃO INICIADO | Half wrong. Role descriptions at the point of choice were already built and tested. The grant list's own rows and its remove-confirmation dialog still rendered the raw `principal_id` — `bootstrap-administrator`, `local-admin`, the exact two strings the problem statement names — unresolved, in `font-mono`. | Role descriptions: DONE (no change). Grant identity: fixed here, test-first |
| 4. "Bootstrap administrator — Not recorded" | NÃO INICIADO | Half wrong. A prior, uncredited pass had already replaced "Not recorded" with the principal's raw `user_id` — better than "Not recorded" reading as a bug, but still a slug, not a sentence saying what the record is. | Fixed here, test-first |
| 5. Issue a token sem escopo | NÃO INICIADO | Wrong — already done. The form asks only "What it is for"; a `token-issued-scopes` line already names the fixed scope a new token gets (this viewer's own permissions), matching the backend's `_scoped()`, which grants an unscoped token (`permissions: []`, what the form sends) exactly its issuer's own permission set. `tokens.test.tsx` already pinned both halves. | DONE (no change) |

## Evidence and corrections

### 1. The token list is a dump — already fixed on all three counts

**Sessions and machine tokens are already two lists, grouped.**
`administration.tsx:14,18,111-128` splits `/identity/tokens`' one answer by
`isConsoleSession` (`token-identity.ts:36-38`, matched against the exact
literal `platform/identity/local_accounts.py:67`'s `CREDENTIAL_NAME` issues
under) before either panel renders anything. `SessionPanel`
(`tokens.tsx:371-482`) groups by `principalId` (`grouped()`, `:344-359`) and
ends every session a person holds through one "end all" control
(`endAll()`, `:379-401`) — never a per-tab revoke. `TokenPanel`
(`tokens.tsx:81-303`) is the separate, still-individually-revocable machine
list. Confirmed by running, not reading, against the unmodified tree:
`pnpm exec vitest run tests/unit/surfaces/tokens.test.tsx` — **all tests
passed**, including `'collapses three logins by the same person into one
row'` and `'ends every session a person holds in one confirmation'`.

**The emission question was already investigated, and fixed.**
`console/src/shell/sidebar.tsx:103-122`'s nav `<Link>` used to default to
`prefetch` (implicitly `true`); commit `bbd74a0` set `prefetch={false}` with
its own comment naming the mechanism directly: "every area here is a dynamic
Server Component that reads live, authenticated data on render, so a default
prefetch would mean every one of the eighteen areas re-runs its API reads on
every single navigation... a stampede the gateway's session handling was not
built to absorb." I traced the sign-in path this screen actually reads from
independently, to confirm there is no separate renewal mechanism this fix
would have left standing: `console/src/app/api/session/route.ts`'s `POST`
calls `/auth/sign-in` exactly once, only on an actual credentialed form
submission; `console/src/session/guard.ts:55-68`'s middleware guard only ever
checks whether the session cookie is *present*, never re-authenticates; and
`platform/identity/local_accounts.py:139-178`'s `LocalSignIn.sign_in` is the
only place a `CREDENTIAL_NAME`-tagged token is minted, gated on a real
username/password pair. `SESSION_LIFETIME_SECONDS`
(`console/src/session/cookies.ts:29`, `43200`) and
`LOCAL_ACCOUNT_SESSION_SECONDS`
(`config/constants/security.py:492`, `12 * 60 * 60`) agree exactly, ruling out
a lifetime mismatch as a second cause. No page-load-triggered re-issuance
exists in the code as it stands; the "~70 sign-ins, three an hour" the
auditor saw is consistent with genuine repeated sign-ins during testing
colliding with the prefetch stampede's extra load on session validation, which
`bbd74a0` already addresses. I did not attempt to reproduce the original
symptom live — that would need a running deployment over time — so this is
reported as traced through the code rather than reproduced.

**Column headers already exist, and the specific ambiguity is gone.**
`tokens.tsx:266-277`'s `token-columns` row names `Token`/`Scopes`/`Expires`;
`SessionPanel`'s `session-columns` row (`:404-413`) names `Person`/`Expires`.
Neither panel renders an issuance timestamp at all any more — only `Expires`,
labelled — so the "in 12 hours" vs "4 hours ago" guess `spec.md` names cannot
recur: whichever tense the relative string reads in, the header says what it
is. `tokens.test.tsx`'s `'columns a value alone cannot explain'` and
`'draws no column header at all over an empty list'` blocks (both files)
already covered this and passed unmodified.

No test was written for this item: everything `controle.md` marked pending was
run, not read, against the unmodified tree, and all of it passed.

### 2. SSO validation before any input — already fixed

`console/src/surfaces/sso.tsx:88-94`: `state.problems` initialises from the
`problems` prop and is replaced only by `adopt()` (`:128-135`), called from
`save()` (`:137-145`) and `makeActive()` (`:168-171`) — never on mount.
`administration.tsx:330-336` passes `problems={[]}` explicitly, with its own
comment naming the exact bug this closes: "Never the deployment's declarative
validation of the document as it stands on load — `SsoForm` renders this list
unconditionally from mount, and the deployment always answers with 'issuer is
required' and seven siblings for a form nobody has touched yet." That is the
literal defect `spec.md` describes ("8 mensagens 'X is required' — antes de o
operador tocar num campo"), already closed. `SsoForm` is called from nowhere
else (`administration.tsx` is its only caller), so there is no second call
site that could reintroduce the eager read. Confirmed by running
`pnpm exec vitest run tests/unit/surfaces/sso.test.tsx` against the
unmodified tree: **21 passed**, including `'offers no way to activate an
untested provider'` and the whole `'the order that keeps somebody from being
locked out'` block. No gap found; no change made.

### 3. Grants and roles in slug — role descriptions already correct, grant identity fixed here

**Role descriptions — already correct, confirmed rather than assumed.**
`administration.tsx:91-96` builds `roleDescriptions` from
`/identity/roles`' own live permission list (`gateway/http/routes/identity.py:362-385`'s
`list_roles`, itself reading `permissions_for(role)` from
`platform/identity/permissions.py`), composed as a comma-joined string rather
than an invented sentence — deliberately, per the module's own comment: "a
second copy would be the copy that goes stale the day a permission is added."
`grants.tsx:261-273` reads `roleDescriptions[role]` as the `<Select>`'s
`description`, changing with the choice. `grants.test.tsx`'s `'what a role
means, at the point it is chosen'` block (3 tests, pre-existing) confirmed
this, unmodified, before this audit touched anything.

I considered whether this satisfies `spec.md`'s "mesmo padrão da spec 031
para níveis de autonomia" as literally as a hand-written sentence would, given
031's own fix used full prose per level. The two are not the same shape by
accident: autonomy levels are a small, permanently fixed enum whose meaning
never changes, so a static catalogue entry per level cannot go stale; a
role's *permission set* is exactly the thing this codebase's own conventions
(`tools/console_roles`, this route's own docstring) treat as the one fact that
must never be duplicated in the console, because it is the one that changes.
Given that, reading the permissions live and showing them at the point of
choice is the correct application of the same principle 031 used, not a
shortcut around it — and it is what `grants.test.tsx` already pins as
correct behaviour (`DESCRIPTIONS = { viewer: 'investigation.read,
report.read', ... }`). No change made here.

**The grant list's own rows — genuinely unfixed, fixed here.**
`grants.tsx:238` (pre-fix) rendered `<span className="font-mono
truncate">{row.principalId}</span>` — the raw id, unresolved, on every row —
and the remove-confirmation dialog's `target` (`:301-306`, pre-fix) built its
own text from `confirmingGrant.principalId` the same way. Both
`bootstrap-administrator` (`config/constants/first_run.py:64`,
`BOOTSTRAP_PRINCIPAL_NAME`'s own id) and `local-admin`
(`config/constants/security.py:479`, `LOCAL_ACCOUNT_PRINCIPAL_ID`) hold an
owner grant on every deployment (`platform/startup/bootstrap.py:407-414`,
`platform/identity/local_accounts.py:197-204`), so a reader of this screen
genuinely sees exactly the two strings `spec.md`'s own text quotes. The
`principals` list the same panel already threads through for its picker
(`GrantPrincipalOption`, `id`+`label`) was never consulted for the rows
already on the page, even though `administration.tsx` had already solved the
identical problem for sessions with `principalLabel` (`:102-107`).

Test-first: `grants.test.tsx`'s new `'who a grant belongs to, at a glance'`
block and the updated `'names the principal and the role before it removes
anything'` assertion. Run against the unmodified component:
`pnpm exec vitest run tests/unit/surfaces/grants.test.tsx` —
**2 failed | 25 passed (27)**. `'shows the display name a principal is known
by, not their raw id'` failed with `TestingLibraryElementError: Unable to
find an element with the text: Avery Lockhart` (the row held only
`user-avery`); the modified `'names the principal and the role before it
removes anything'` failed on `expect(within(dialog).getByText('Avery
Lockhart — owner'))`, the dialog still reading `user-avery — owner`.
Confirmed red for the right reason. `'falls back to the raw id for a
principal this console has no label for'` passed trivially against the
unmodified code, because a raw id was already what rendered for an
unresolved principal — a regression guard going forward, not a pin, and this
report says so rather than counting it as one.

Fixed by `grants.tsx:100-116` (`principalLabel`, new) and its two call sites
(`:238-240`, the row; `:322-326`, the confirmation dialog's `target`):

```tsx
function principalLabel(
  principals: readonly GrantPrincipalOption[],
  principalId: string,
): string {
  const found = principals.find((option) => option.id === principalId);
  return found === undefined || found.label === '' ? principalId : found.label;
}
```

Resolved from `GrantPanel`'s own `principals` prop rather than added as a new
field on `Grant`, because it already carries the answer for the picker above
and a row optimistically added from the deployment's own POST response
(`grant()`, `:172-204`) needs resolving the identical way a row the screen
served does, with one lookup rather than two that could disagree. After the
fix: **27 passed**.

### 4. "Bootstrap administrator — Not recorded" — half-fixed by a prior pass, finished here

`administration.tsx:170-184` (pre-fix) read:

```tsx
{text(person, 'email') === ''
  ? text(person, 'user_id')
  : text(person, 'email')}
```

with a comment already correctly diagnosing the problem ("'Not recorded' here
reads as a bug rather than as what it is") but resolving it to the raw
`user_id` (e.g. literally `bootstrap-administrator`) rather than to a
sentence — an improvement over `spec.md`'s literal complaint, but not what
its own suggested fix asks for ("Dizer o que é ('conta de serviço criada no
deploy, sem e-mail')"). Confirmed the shape of the account this affects by
reading `platform/startup/bootstrap.py:399-406`'s `_ensure_bootstrap_principal`
directly: `email=""`, `display_name=BOOTSTRAP_PRINCIPAL_NAME` ("Bootstrap
administrator"), `kind=PrincipalKind.SERVICE_ACCOUNT` — and confirmed, by
reading `gateway/http/routes/identity.py:186-193`'s `_user_view` and
`platform/identity/local_accounts.py:189-196`'s local-account principal (which
now carries a synthetic `@localhost` email, so it no longer hits this branch
at all), that a blank email on this deployment's identity model means exactly
one thing: a service account nobody gave one, by construction, never a person
whose email this deployment simply failed to record.

Test-first: a new file, `console/tests/unit/surfaces/administration.test.tsx`
(this screen had no dedicated test file before, unlike every other screen —
`resources.tsx`, `dashboard.tsx`, etc. all have one — because until this
change every other piece of this screen's own logic lived in a tested
subcomponent; this one line of logic did not), testing the newly-exported
pure function directly, the same pattern `agent.test.tsx` already established
for `budgetLabel`/`effectiveBudget`/`roleBinding`. Run against the tree with
no implementation yet: `pnpm exec vitest run
tests/unit/surfaces/administration.test.tsx` — **4 failed (4)**, every one
`TypeError: principalIdentity is not a function` — confirmed red (the
function did not exist at all).

Fixed by `administration.tsx:59-77` (`principalIdentity`, new, exported):

```tsx
export function principalIdentity(locale: Locale, person: unknown): string {
  const email = text(person, 'email');
  if (email !== '') return email;
  return text(person, 'kind') === 'service_account'
    ? message(locale, 'admin.principals.serviceAccount')
    : text(person, 'user_id');
}
```

wired in at `:192`, with two new catalogue entries:
`admin.principals.serviceAccount` — "A service account created at deploy,
with no email." (`en.ts:1161-1162`), "Conta de serviço criada no deploy, sem
e-mail." (`pt-BR.ts:1036`) — the Portuguese chosen to echo `spec.md`'s own
suggested wording almost verbatim. The non-service-account, blank-email
branch (falling back to the raw id) is kept rather than removed: the current
identity model never produces that case, but nothing in this function should
assume it never will, and it is the same "show the id rather than nothing"
choice `administration.tsx`'s own `principalLabel` closure already makes for
an unrecognised session principal. After the fix: **4 passed**.

**The mock's own `kind` vocabulary — traced, found wrong, and corrected.**
None of `fixtures/scenarios/`'s committed principals were, at first, a
`service_account`/blank-email combination — but that turned out not to be
the whole finding. Every principal the mock plane served spelled `kind` as
`"person"`/`"machine"`
(`tools/mockplane/dataset/served.py`'s `USERS` and `identity_records()`,
`tools/mockplane/dataset/build.py`'s `empty_records()`), while the real
backend's `PrincipalKind` enum
(`platform/persistence/ports/identity_repository.py:26-30`) declares exactly
two values, `"user"` and `"service_account"`, confirmed independently by
`gateway/http/routes/identity.py:186-193`'s `_user_view`, which reads
`user.kind.value` straight off that enum with no translation in between.
That is the wrong side of the divergence, and it is not cosmetic:
`principalIdentity`'s branch keys on `kind === 'service_account'` exactly,
so a mock that never serves that value never exercises the branch on
anything a fixture-driven suite — or an operator looking at the mock-plane
demonstration deployment — actually sees; only this confrontation's own
direct unit test did, which is what the first pass of this report understated
as a scope boundary rather than named as the real gap it was.

Corrected across the vocabulary's one source rather than patched per
scenario: `served.py`'s `USERS` now declares `"user"` for the three people
and `"service_account"` for the one machine account (`Scheduler`), and both
of the two places that used to repeat `"person"` as a second literal
(`identity_records()`'s own `"principal"` body, and `build.py`'s
`empty_records()`'s) now read `display["kind"]`/`served.USERS[0]["kind"]` off
that one declaration instead, so this cannot drift back to a second, wrong
copy the way it had. Every committed scenario was rebuilt with
`uv run python -m tools.mockplane build` (`populated`, `empty`, `first-run`,
`restricted` — `degraded` and `scale` hold no committed files of their own and
inherit `populated`'s corrected data). Checked, specifically, before making
the change: whether the console's own source or the mock plane's own runtime
code branches on the literal strings `'person'`/`'machine'` anywhere, which
would have made this a two-part fix. Neither does.
`console/src/design/status.ts`'s `DECLARED` map has no entry for any of the
four spellings, so the kind badge already rendered the API's own raw text
verbatim on both sides of the change — only the text itself moves. Sixteen
*test* files across unrelated screens (`resources.test.tsx`,
`incidents.test.tsx`, `autonomy.test.tsx`, and thirteen more) hand-build their
own `PRINCIPAL` stub with a literal `kind: 'person'`, but `Viewer`
(`console/src/session/viewer.ts`) has no `kind` field at all — `parseViewer`
never reads it — so every one of those is inert scaffolding matching the
wire shape rather than logic that keys on the value; none needed changing,
and none regressed (confirmed by re-running the full console unit suite,
below). `console/tests/unit/support/dataset.ts:209`'s own
`principalHolding()` — the shared helper most cross-screen tests actually
build their `/auth/me` stub from — already used `kind: 'user'`
independently, corroborating which side was correct before this fix touched
anything.

A related, second divergence was traced and left alone, named rather than
folded into this fix: `AUDIT_EVENTS`
(`tools/mockplane/dataset/served.py:2019-2108`) spells `actor_kind` as
`"person"`/`"machine"` too, and the real `ActorKind` enum
(`platform/persistence/ports/audit_repository.py:28-38`) has neither —
its four values are `"user"`/`"token"`/`"agent"`/`"system"`. This is a
genuine, real mismatch of the identical shape, but it feeds `/audit/events`,
which belongs to the Audit screen (spec 038), not this one; nothing in this
confrontation's own `spec.md` reaches it, and no code this confrontation
touched reads `actor_kind`. Named here so the next confrontation that
reaches Audit does not have to rediscover it.

Test-first, for the vocabulary fix itself: a new test,
`test_every_principal_kind_is_one_the_backend_actually_declares`
(`tests/contract/fixtures/test_dataset_contract.py:100-124`), asserting every
`"principal"`/`"principals"` record any built scenario serves carries a
`kind` that is a member of the real `PrincipalKind` enum — read live from
`platform.persistence.ports`, not copied as a second list of allowed
strings. Run against the unmodified generator, before either Python file was
touched: **1 failed**, naming every offending record by scenario and slug
(`populated/principal: 'person'`, `populated/principals: 'person'` ×3,
`populated/principals: 'machine'`, and the same pattern repeated for `empty`,
`first-run`, `degraded`, `incident-live`, `restricted` and `scale` through
inheritance — 28 offending records across all seven declared scenarios).
Confirmed red for exactly the reason named. After the fix and the rebuild:
**1 passed**, and the full `tests/contract/fixtures/` suite —
**102 passed** (101 recorded by this confrontation's own first pass, +1 for
the new test) — including `test_rebuilding_the_dataset_reproduces_what_is_committed`
and `test_two_builds_of_one_scenario_are_byte_identical`, confirming the
rebuild is itself stable and reproducible, not a one-off.

### 5. Issuing a token with no visible scope — already fixed

`tokens.tsx:93-119`'s `issue()` sends `{ name, permissions: [] }` — the form
asks only "what it is for," matching `spec.md`'s own description. What
`permissions: []` actually produces was traced on the backend rather than
assumed: `platform/identity/tokens.py:572-589`'s `_scoped()` docstring states
it directly — "An unscoped token is a personal access token and carries no
cap — it is as wide as its owner." `administration.tsx:287` passes
`issuedScopes={viewer.permissions}`, and `tokens.tsx:251-255` renders it as
`token-issued-scopes`: "Scopes: {issuedScopes.join(', ')}" — a true statement
about what the token this form issues actually gets, satisfying `spec.md`'s
"Se é fixo, dizer qual" branch exactly. `tokens.test.tsx`'s `'what a token
issued here actually holds'` block (2 tests, pre-existing) already pinned
this and passed unmodified before this confrontation touched anything.

### A Brazilian-Portuguese sweep, on this screen's own catalogue block

Found while reading `pt-BR.ts`'s `admin.*` block for the lines items 3 and 4
needed, the same way 022's, 031's and 033's confrontations found theirs — not
a repository-wide sweep.

```
pt-BR.ts:1038  'admin.column.active': 'Activa'                → 'Ativa'
pt-BR.ts:1088  'admin.sso.activating': 'Activando…'            → 'Ativando…'
pt-BR.ts:1089  'admin.sso.active': 'Activo. As pessoas...'     → 'Ativo. As pessoas...'
pt-BR.ts:1091  '...Não pode ser activado enquanto...'          → '...ativado...'
pt-BR.ts:1093  '...antes de a activar...'                      → '...antes de a ativar...'
```
The silent-consonant class 022's confrontation already fixed for
`Objectivo`/`Activar` elsewhere. Confirmed which spelling this catalogue has
actually settled on before touching either: `Ativ-` already appears seven
times, clean, across `detectors.*`, `schedules.*`, `approvals.*`,
`autonomy.*` and `catalogue.*` (`pt-BR.ts:579,659,675-678,696-701,847,989`);
`Activ-` appears nowhere else *except* two other screens' own blocks —
`shell.guardian.active` (`:295`) and `dashboard.activity.*`/`.guardian.*`
(`:439-460`) — named here, not touched, because they belong to the shell
chrome and to Dashboard (spec 010), not to this screen.

```
pt-BR.ts:1078  'admin.sso.redirect': 'Redireccionar de volta para' → 'Redirecionar de volta para'
```
The only `Redireccion-` in the catalogue (double-c, European); the Brazilian
form drops the silent consonant the same way `direcção`/`direção` already
does elsewhere in this repository's own orthography.

```
pt-BR.ts:1079  'admin.sso.defaultNode': 'Equipa por omissão'   → 'Equipe padrão'
```
Two defects in one line. `equipa` (European) was the *only* remaining
instance of that spelling anywhere in the catalogue — every other screen
already reads `equipe` (confirmed by a repository-wide search, six clean
instances including `nav.teamContext`, already corrected by 033's own sweep).
`por omissão` (European, "by default") has no sibling anywhere either; this
catalogue's own established word for the same concept is `padrão`
(`approvals.empty.rule.default`, `configuration.editor.usingDefault`,
`agent.models.default`, three independent confirmations).

```
pt-BR.ts:1086  '...para um utilizador de teste...'             → '...para um usuário de teste...'
```
`utilizador` (European "user") appears exactly twice in the whole catalogue —
this line, and `signIn.rejected` (`:349`) — with `usuário` (Brazilian)
appearing nowhere at all yet to compare against; fixed here because it is on
this screen, named but not touched on the Sign-in screen because that belongs
to a different surface.

**Found and deliberately not touched: the wider "a + infinitive" continuous
construction.** `admin.tokens.revokeCancel` (`:1064`, pre-existing, unchanged)
reads "Deixar a funcionar" ("leave it working") — the same PT-PT-style
continuous-aspect marker ("deixar a X" for "leave X running") the whole
catalogue already uses in at least seven other places across at least five
other screens' own blocks: `stop.cancel` ("Deixar a correr", `:282`,
shell/stop.tsx — the topbar's own analogous cancel control for the identical
"leave it running" idiom), and prose in `failure.migrations.title` (`:323`),
`surface.loading`'s sibling at `:360`, `dashboard.attention.empty.action`
(`:424`), and `approvals.empty.action` (`:576`). This is not the same defect
class as the `"A + infinitivo…"` status-label shorthand 033's confrontation
already fixed for `teamContext.saving`/`.previewing` (this screen's own
status labels — `Emitindo…`, `Revogando…`, `Guardando…`, `Testando…` — are
already correctly gerund-form and needed no change). Given the breadth of
this one — eight instances spanning shell chrome, Dashboard, Approvals and
Failure, none of it named by any of `spec.md`'s five items, and
`admin.tokens.revokeCancel`'s own copy appears to deliberately mirror
`stop.cancel`'s established wording for the same UI pattern — fixing this
screen's one instance alone risked creating exactly the inconsistency 033's
confrontation was corrected for treating a sibling screen as out of scope.
Named here, left alone, for whichever confrontation next reaches this pattern
catalogue-wide.

All corrections were re-confirmed with a case-insensitive re-grep of the
whole `admin.*` block afterward: none of `Activ`, `Redirecc`, `equipa`, `por
omissão`, or `utilizador` remains inside it.

### Traced and confirmed not the mechanism in play: `platform/identity/sessions.py`

Offered no hint by `spec.md`, but found while tracing item 1's emission
question: `platform/identity/sessions.py`'s `SessionStore`/`Session` is a
second, signed-cookie session mechanism (`issue`/`validate`/`touch`, its own
idle and absolute lifetimes) distinct from the bearer-token flow
`LocalSignIn` actually issues through. Confirmed by tracing every caller of
`LocalSignIn.sign_in` and of `SessionStore.issue` separately: the console's
own `/api/session` route and everything this screen reads
(`/identity/tokens`) go exclusively through the token-based path; nothing
under `platform/identity/sessions.py` is in that call chain. Named so it is
not mistaken for the mechanism behind this screen's own data the next time
someone traces the same question.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/tokens.test.tsx
  tests/unit/surfaces/sso.test.tsx tests/unit/surfaces/grants.test.tsx` — run
  **before any change**: all passed, confirming items 1, 2 and 5, and item
  3's role-description half, by running them rather than trusting
  `controle.md`'s account.
- `pnpm exec vitest run tests/unit/surfaces/grants.test.tsx` — after adding
  the new/modified assertions for item 3's grant-identity half, **before**
  the fix: **2 failed | 25 passed (27)**, confirmed red for the reasons
  quoted above. After the fix: **27 passed**.
- `pnpm exec vitest run tests/unit/surfaces/administration.test.tsx` (new
  file) — before `principalIdentity` existed: **4 failed (4)**, every one
  `TypeError: principalIdentity is not a function`, confirmed red. After the
  fix: **4 passed**.
- `pnpm exec vitest run tests/unit/surfaces/grants.test.tsx
  tests/unit/surfaces/tokens.test.tsx tests/unit/surfaces/sso.test.tsx
  tests/unit/surfaces/administration.test.tsx tests/unit/i18n
  tests/unit/surfaces/screens.test.tsx tests/unit/shell/role-matrix.test.tsx`
  — **295 passed (8 files)**, confirming the catalogue completeness/fallback
  tests and the cross-screen empty/error/populated/role-matrix smoke suite
  all still hold with the new keys and the changed rendering in place.
- `pnpm exec vitest run` (full unit suite) — **2017 passed (123 files)**, net
  +6 tests and +1 file over the 2011/122 recorded by 035 Agent's own
  confrontation at this exact `HEAD` (`506f942`, confirmed clean before this
  session touched anything) — exactly the 2 new `grants.test.tsx` tests plus
  the 4 new `administration.test.tsx` tests, no other file's count moved. One
  benign jsdom console line ("Not implemented: navigation to another
  Document") is the same pre-existing test-environment noise every prior
  confrontation in this series has recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/screens/administration.tsx
  src/surfaces/grants.tsx src/i18n/en.ts src/i18n/pt-BR.ts
  tests/unit/surfaces/administration.test.tsx
  tests/unit/surfaces/grants.test.tsx` — clean.
- `pnpm exec prettier --check` on the same six files — two needed `--write`
  once (`grants.tsx`, `en.ts` — line-wrap only, from the new function
  signature and the new catalogue entry); reformatted, `--check` passed
  clean afterward, and `grants.test.tsx`, `administration.test.tsx` and
  `tests/unit/i18n` were re-run to confirm the reformat changed nothing
  behaviourally (**55 passed**).
- `make console-client-check` — clean; `git status` on `src/api/schema.ts`
  and `fixtures/contract/openapi.json` shows no diff, confirming no backend
  contract changed (none was touched — every change in this confrontation is
  console-only).
- `make console-build` — succeeded, all routes including `/administration`
  compiled, run before every build-dependent gate below per the standing
  instruction that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged (no new token, no new icon).
- `make console-visual` — run **twice**. First, after the console-only
  changes (grants/administration): **34 passed, 1 failed**,
  `administration-1440-light` (1362 pixels, 0.01 ratio) — the Grants panel's
  four rows reading resolved principal names in place of their raw ids.
  Second, after the mock plane's vocabulary was corrected and the committed
  scenarios rebuilt: **34 passed, 1 failed** again, the same screen, now
  **2269 pixels** (0.01 ratio) — a strictly larger, reproducible diff. The
  new diff image was inspected directly and shows exactly the additional,
  expected change on top of the first: the Principals panel's four kind
  badges now reading `USER` ×3 and `SERVICE_ACCOUNT` (was `PERSON`/`MACHINE`),
  with nothing else on the page altered by either pass. Per instruction,
  **this baseline is not accepted here** — left for the orchestrator to
  review and recapture, once, for both changes together.
- `make console-e2e` — run **twice**, before and after the fixture
  correction: **84 passed (0 failed)** both times, across both Playwright
  projects (`behaviour`, 79; `first-day`, 5). No test in this suite exercises
  Administration specifically by name; this confirms neither change disturbed
  sign-in, navigation, or any other flow the suite already walks.
- `pnpm exec vitest run` (full unit suite) — re-run in full a second time,
  after the fixture correction and rebuild: **2017 passed (123 files)**,
  identical to the count above — confirming no console test reads the
  fixture's `kind` value in a way the correction could have disturbed.
- `make console-budget` and `make console-client-check` — re-run after the
  fixture correction: unchanged, clean; no schema or client diff (this
  confrontation's Python changes are in the mock's own generator, not the
  gateway's OpenAPI document).
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after every browser/contract run,
  the same housekeeping every prior confrontation in this series has
  recorded.

Python, from the repository root:

- `uv run python -m pytest tests/contract/fixtures/test_dataset_contract.py::test_every_principal_kind_is_one_the_backend_actually_declares`
  — run **before** `served.py`/`build.py` were touched: **1 failed**, naming
  28 offending records across all seven declared scenarios (quoted in full
  under item 4's evidence above) — confirmed red for the exact reason named.
  After the fix and `uv run python -m tools.mockplane build`: **1 passed**.
- `uv run python -m pytest tests/contract/fixtures/ -q` — run twice: **101
  passed** before this confrontation's Python change (matching the count
  already recorded by the first pass above), **102 passed** after (the one
  new test), including `test_rebuilding_the_dataset_reproduces_what_is_committed`
  and `test_two_builds_of_one_scenario_are_byte_identical` — confirming the
  rebuild this confrontation ran is itself stable and reproducible.
- `uv run python -m pytest tests/contract/console/ -q` — run **twice**. Before
  the fixture correction: **1 failed, 297 passed** (315.37s). After: **1
  failed, 297 passed** again (324.67s) — the same single failure both times,
  `test_console_visual_regression.py::test_the_untouched_baselines_still_match`,
  the Python-side mirror of the visual gate above, failing on the identical,
  self-caused, already-confirmed `administration-1440-light` diff each time
  (larger the second run, matching `make console-visual`'s own second result)
  — not a second, independent failure. `test_console_shell.py` (holding the
  route/permission table this report's permission cross-check relies on) is
  among the 297 passes both times.
- `uv run ruff check`, `uv run ruff format --check` and `uv run mypy` on the
  three Python files this confrontation changed
  (`tools/mockplane/dataset/served.py`, `tools/mockplane/dataset/build.py`,
  `tests/contract/fixtures/test_dataset_contract.py`) — all three clean.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
  was not re-run — no file this confrontation touched could affect it.

**On confirming new tests red first.** Every genuinely new assertion —
`grants.test.tsx`'s new principal-identity block and its one modified
assertion, all four of `administration.test.tsx`'s tests, and
`test_every_principal_kind_is_one_the_backend_actually_declares` — was
confirmed red against the code exactly as it stood immediately before its
own fix, in the words quoted above, not inferred. One new assertion
(`'falls back to the raw id for a principal this console has no label for'`)
passed trivially against the unmodified code, and this report says so rather
than counting it as a pin — it stands as a regression guard going forward.
Items 1, 2 and 5, and item 3's role-description half, needed no new test:
the existing tests `controle.md` marked pending or partial were *run*, not
read, against the tree exactly as this confrontation found it, and all
passed — the convention 021 Topology's, 023 Memory's, 024 Knowledge's, 031
Autonomy's, 033 Team Context's and 035 Agent's confrontations used for the
same situation.

## Control reconciliation

`specs_v4/036-administration/controle.md` is rewritten so every row states
the verified status and points at this report. Items 1, 2 and 5 move from
`PARCIAL`/`NÃO INICIADO` to `FEITO`: no code changed for any of the three,
only the verdict, with item 1's detail correcting the specific claim that
separation, headers and the emission investigation were "pendentes" — all
three were already done. Items 3 and 4 move from `NÃO INICIADO` to `FEITO`,
each split into what was already correct (role descriptions; the "Not
recorded" → raw-id half-fix) and what was genuinely built here (grant-row and
confirmation-dialog identity resolution; the service-account sentence,
replacing the raw-id fallback, in both locales) — item 4's own detail also
records the correction made after coordinator review: the mock data plane's
`kind` vocabulary, first traced and left to `tools/mockplane`'s own surface
as a named-but-untouched divergence, was in fact the reason item 4's fix was
verified only in isolation, and is corrected in this same pass (`served.py`,
`build.py`, every committed scenario rebuilt, one new contract test). A
closing note records: the Brazilian-Portuguese corrections made in this
screen's own `admin.*` block (five silent-consonant `Activ-`→`Ativ-`
instances, `Redireccionar`→`Redirecionar`, `Equipa por omissão`→`Equipe
padrão`, `utilizador`→`usuário`); the wider "a + infinitivo" continuous
construction found spanning at least five other screens' own blocks, named
but not touched; the dashboard/shell `Activ-` instances and the Sign-in
screen's own `utilizador`/`palavra-passe`, named but not touched, belonging
to other screens; the dead, unused `admin.column.kind` catalogue entry,
found while searching specifically for 035's empty-lookup-table defect shape
and confirmed to be a different, smaller shape (an unwired column header,
not a populated-but-empty map) that nothing in `spec.md`'s five items asks to
be wired up; the identical `"person"`/`"machine"` divergence found in
`AUDIT_EVENTS`'s own `actor_kind` field, against the real, different
`ActorKind` enum — a genuine second instance of the same defect shape, left
named rather than fixed because it feeds the Audit screen (spec 038), not
this one; and `platform/identity/sessions.py`'s separate `SessionStore`,
traced and confirmed not to be the mechanism behind this screen's own data.
