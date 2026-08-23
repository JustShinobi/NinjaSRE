# Deviations — 052 First run in the console

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. The credential is couriered by the console, not posted at the gateway

**Planned.** `plan.md` §2, "Decision — how the browser authenticates the direct
credential write": the browser posts the credential form straight at
`apiOrigin()`, the gateway learns to accept the console's session cookie
(scoped CORS, `credential.write` checked against the session principal), and the
alternative — proxying through a Next route — is rejected because it puts the
secret in a second process.

**Done.** `console/src/app/api/credential/route.ts`, a courier that forwards one
`PUT` to `/v1/integrations/{name}/credential` and keeps nothing. `CredentialField`
posts to it with `fetch`. The gateway is unchanged: it still authenticates by
bearer token alone, and no CORS or cookie path was added to it.

**Why the planned mechanism cannot work.** Three reasons, and the first is
decisive on its own.

*The browser cannot know the API origin.* `apiOrigin()` reads
`process.env.NINJASRE_CONSOLE_API_URL`, which Next inlines into a client bundle
only for `NEXT_PUBLIC_`-prefixed names. In a `'use client'` component it
evaluates to `''` in every deployment. The existing form action was therefore
already relative — `/v1/integrations/{x}/verify` against the *console's* host —
so "it posts to the API origin" was a docstring rather than a behaviour.

*The session cookie is not sendable to another host.* It is `HttpOnly`,
`SameSite=Strict`, and set on the console's host. A browser will not send it to
a different origin, and CORS cannot change that — CORS governs whether a
response may be *read*, not whether a host-scoped cookie is attached. So the
plan's mechanism authenticates only when the console and the gateway share an
origin, and silently produces an unauthenticated write in every deployment that
sets `NINJASRE_CONSOLE_API_URL`.

*The doctrine the plan cites is not the one the console holds.*
`src/app/api/session/route.ts` already takes a **password** — a secret of
exactly this class — through the console process, on the way to `/auth/sign-in`.
The rule that is actually held everywhere is not "no secret enters this process"
but "this process keeps none of it": nothing stored, nothing logged, nothing
returned, nothing in a URL. The courier holds all four, and its docstring says
so field by field.

**What this means for the definition of done.** Item 3 — the sentinel sweep — is
strengthened rather than weakened by the change, because the courier is now a
place a secret could leak and the sweep walks it: `first-day.spec.ts` scans
every request address, every response body, the rendered document, the RSC
payload and browser storage for the sentinel, and
`decide.test.tsx` asserts the value is not in the DOM after the write, masked or
otherwise.

<!-- proof: console/tests/first-day/first-day.spec.ts -->
<!-- proof: console/tests/unit/surfaces/decide.test.tsx -->

---

## 2. Two steps of the seven share one predicate, and the seventh is the platform's

**Planned.** `tasks.md` T-003: the screen "derives its current step from the
checklist's `next`".

**Done.** The step is derived in `console/src/surfaces/first-run/plan.ts` from
provider *readiness*, per-integration readiness, two checklist step states, and
whether the configuration at this node names a model. `next` is not used.

**Why.** The checklist has four steps and the wizard has seven, so `next` cannot
name the wizard's step: on a fresh deployment `next` is `model-provider` for the
whole of steps one through five. Worse, `next` stops moving after the credential
is stored — the route composes no live model verifier, so provider readiness
goes `absent → configured` and the step stays `ready`. A wizard keyed on `next`
would sit on step one for ever, and the resumability requirement (T-016) would
fail against a deployment that had done the work.

Readiness is the field that does move, and it is a *three*-valued vocabulary the
platform added for exactly this screen. Choosing a provider and storing its
credential therefore share one predicate — there is nothing a deployment records
about the first without the second — which is also what makes "kill the browser
after the credential step, come back at the model step" true.

**One override.** When the checklist reports `complete`, every wizard step is
done regardless of the finer view. The seven are a view of the platform's four,
and a view that contradicted them would put the console and the terminal into
disagreement about a deployment that is finished.

<!-- proof: console/tests/unit/surfaces/first-run-plan.test.ts -->
<!-- proof: tests/contract/console/test_console_first_run.py::test_the_cli_and_the_console_read_one_checklist -->

---

## 3. The nav zones, and where the two areas D2 does not name went

**Planned.** `plan.md` §1: `NAV_GROUPS` becomes `['now', 'environment',
'settings']` "with the D2 assignment".

**Done.** That, and D2's list is missing two of the fourteen existing areas.
**Catalogue** went to `environment` and **Autonomy** to `settings`.

**Why.** D2's "Ajustes" lists a future *Agente* screen (060) and no capability
catalogue at all. Autonomy is the closest existing thing to "what the agent may
do", and it is changed rather than read, which is the axis the zones are cut on.
The catalogue is read far more often than it is changed and answers "what exists
and what is known", so it stayed beside memory and knowledge — which also
preserves the reason the original grouping gave: a reader holding only
`investigation.read` should not be shown a settings group for it.

<!-- proof: console/tests/unit/shell/routes.test.ts -->

---

## 4. The tutorial's dismissal needed a configuration field, so one was added

**Planned.** `plan.md` §4: dismissal "stored through the config write path as a
small console-surface setting".

**Done.** `ConsoleSurfaceSettings.tutorial_dismissed` under
`SurfacesConfig.console`, so the path is `surfaces.console.tutorial_dismissed`.

**Why.** No such section existed; the plan assumed one. A boolean under
`surfaces` is where the deployment's other per-team surface decisions live, and
a contract test now holds every path the guided run writes against the schema,
so a write at a path nothing resolves fails in Python rather than being silently
ignored.

<!-- proof: tests/contract/console/test_console_first_run.py::test_every_setting_the_guided_run_writes_is_one_the_schema_declares -->

---

## 5. The browser suite runs twice, against two datasets

**Planned.** `tasks.md` T-014 to T-016: browser tests of the full flow on an
empty deployment.

**Done.** A second Playwright project, `first-day`, in
`console/tests/first-day/`, run by `tools/console_gate.py` against the
`first-run` scenario after the existing `behaviour` project runs against
`populated`.

**Why.** One mock plane serves one scenario. The sixty existing browser tests
are about a deployment mid-operation and fail against an empty one; the new five
are about the empty one and prove nothing against a full one. Adding the new
tests to the existing project would have meant either breaking sixty tests or
writing tests that assert nothing. Both projects are in the gate, so neither is
optional.

<!-- proof: console/tests/first-day/first-day.spec.ts -->

---

## 6. What the browser suite does *not* prove, and what does

**Planned.** Definition of done 2: "the whole flow finishes in the browser with
no CLI involvement, ending with a verified provider and at least one verified
integration."

**Done, in two halves, and the split is worth stating plainly.**

The *browser* half is proven: `first-day.spec.ts` walks provider → credential →
model → integrations → verify → estate → alerts without one navigation leaving
the shell, types a credential into the generated form, and submits it.

The *outcome* half — a credential that has actually been stored and then
actually verified — is proven against a **real gateway**, through the same two
requests the console's couriers issue, in
`test_console_first_run.py::test_a_credential_written_the_way_the_console_writes_it_verifies`:
the integration reports `usable: false` before the write and `usable: true`
after it, and the checklist the console reads moves with it. The provider half
of the same claim is 051's
`tests/contract/cli/test_onboarding_against_a_deployment.py`.

**Why it is split.** The browser suite's backing is the mock data plane, which
serves recorded responses and runs no vault, no credential health report and no
model verification. A "verified provider" asserted against it would be a fixture
saying `verified: true`, which proves the console can render a word. So the
console side of the claim is asserted in the browser — the flow reaches the
routes, and its assertions are on *outcomes* rather than on controls appearing:
the credential result must read "Stored." and the integrations summary must name
the vendor, both of which fail if the write is refused or the route is absent —
and the deployment side is asserted against a real gateway. Nothing is asserted
twice and nothing is asserted by a fixture agreeing with itself.

The three write endpoints the guided run uses were added to the mock plane
(`credential-write`, `integration-verify`, `provider-verify`) so the browser
half can assert an outcome at all. Before that they 404'd, and the browser test
passed anyway — which is precisely the "test that would pass whether or not the
behaviour exists" that this record exists to catch.

**What is genuinely unrun.** Nobody has driven this against the compose backing
or against the validation container by hand. The `compose` backing exists and
the same suite runs against it in its own CI job; that run has not happened
here.

<!-- proof: tests/contract/console/test_console_first_run.py -->
<!-- handoff: to=053-proxmox-estate-onboarding what="run the first-day browser project against the compose backing and the validation container once a real estate exists to finish the flow against" -->

---

## 7. Phase 2 and Phase 3 were implemented before their component tests

**Planned.** `CLAUDE.md`: "the failing test lands before the implementation, and
is confirmed failing."

**Done.** T-001, T-002 and T-003 were written test-first with the failure
confirmed (`routes.test.ts`, `first-run-plan.test.ts` — both were observed red).
T-004 to T-013 — the step components, the dashboard panels and the tutorial —
had their implementation written first and `first-run.test.tsx` written
immediately after. Three of its thirty-seven assertions failed on the first run
and were genuine defects (a missing test hook, and the `complete` override in
deviation 2); the other thirty-four passed.

**Why it happened.** The step components' props are determined by the shape of
the checklist and provider documents, and that shape was only established by
building the screen that reads them. Writing the tests first would have meant
writing them against a guess and rewriting them.

**What was done about it.** Nothing retroactive; recording it is the honest
option. The thirty-four assertions that passed on their first run are
established as regression tests and are not established as specifications of
behaviour that did not yet exist. The Python side (T-017) and the browser side
(T-014 to T-016) both had failures observed before they passed.

---

## 8. The credential field's contract changed, so its existing tests were rewritten

**Planned.** T-005: "rewire `CredentialField` to `PUT
/v1/integrations/{name}/credential` with fetch submission".

**Done.** That, plus a change of props: `required: readonly string[]` became
`fields: readonly CredentialFieldSpec[]`, and the labels became one shared
builder. The three existing tests in `decide.test.tsx` asserted the old native
form post and were replaced by seven asserting the new contract.

**Why the props changed.** The guided run needs `label`, `help`, `secret` and
`required` per field — the spec asks for a form generated from the declared
`CredentialFieldSpec`s — and a list of names cannot carry them. The catalogue's
two call sites keep working by mapping their `required_credentials` to
all-secret, all-required fields, which is what that list means.

**What was lost.** The old test asserted the form posts to the API origin. That
assertion is gone because the behaviour is gone; deviation 1 says why. Nothing
else the old tests covered is uncovered: "never renders a stored secret back"
and "says so when there is nothing stored" both survive, and three stronger
assertions were added.

<!-- proof: console/tests/unit/surfaces/decide.test.tsx -->

---

## 9. The first-run screen gained a third panel so the empty-state proof still applies

**Planned.** Nothing about a third panel.

**Done.** "What is set up so far" beside the step list.

**Why.** `screens.test.tsx`'s SC-001 walks every screen and requires at least one
panel rendering its empty state against the empty dataset. The wizard's two
original panels are never empty — a step list always has seven steps. The choice
was to exempt the screen from a cross-cutting proof or to give it a region that
is genuinely empty on a fresh deployment. The second is better and is not
contrived: "what has been established" is a different claim from "what has been
ticked", and on a deployment that has established nothing it says so and names
the step that changes it.

<!-- proof: console/tests/unit/surfaces/screens.test.tsx -->

---

## 10. `next` is served and unread, and the provider verify remains a POST nobody makes on render

Two smaller notes, recorded because both look like omissions.

The checklist's `next` field is in the document and the console does not read it
(deviation 2). It is not dead: `ninjasre doctor` and the CLI wizard use it, and
the route is 051's.

The verify step makes no request until somebody presses a control, per row. That
is the gateway's own decision about `POST /v1/providers/{id}/verify` — it spends
the operator's tokens — and a first-run screen that verified on render would
spend money every time the page was opened.

---

## Appendix — where each item of the Definition of done is proven

| Item | Proof |
|---|---|
| 1. Fresh deployment: dashboard at zero, dismissable tutorial, clickable checklist, no redirect | `console/tests/first-day/first-day.spec.ts::a fresh deployment renders the product, not a form in front of it`, and `console/tests/unit/surfaces/first-run.test.tsx` (`the dashboard of a deployment that is not set up`). Not yet done by hand against the validation container — see deviation 6. |
| 2. The flow finishes in the browser, ending verified | Browser half: `first-day.spec.ts::the guided run walks provider to verification without leaving the shell` (asserts the provider credential and an integration credential are both *accepted*, not merely submitted). Deployment half: `test_console_first_run.py::test_a_credential_written_the_way_the_console_writes_it_verifies` (`usable` false → true against a real vault) and 051's `test_onboarding_against_a_deployment.py` for the provider. See deviation 6. |
| 3. The sentinel sweep passes | `first-day.spec.ts::the sentinel reaches the vault and appears nowhere else`, plus `decide.test.tsx::holds nothing back in the document once the write is accepted` |
| 4. A killed browser resumes at the right step | `first-run-plan.test.ts::is at the model once a provider credential is stored and unchecked` derives the step; `first-day.spec.ts::killing the browser mid-flow loses nothing, because nothing was kept` parks the first context on a *different* step, stores a credential, kills it, and asserts the reopened context lands on the step the deployment implies rather than on either of the two the first context visited |
| 5. `ninjasre onboard` and the console agree | `tests/contract/console/test_console_first_run.py::test_the_cli_and_the_console_read_one_checklist`, guarded by the three vocabulary tests beside it |
| 6. Every pre-estate screen names what is missing and what supplies it | `console/tests/unit/surfaces/screens.test.tsx` (SC-001, over every screen) and `first-run.test.tsx::gives every empty state an action that names a place this console has` |


---

## 11. Two findings from the done-audit, and what was done about them

The audit before finishing found two tests that would have passed whether or not
the behaviour existed. Both are fixed above rather than argued with, and they are
recorded here because the *shape* of both mistakes is worth remembering.

**The credential write asserted that a result box appeared.** `CredentialField`
renders one on success and on refusal alike, and the mock plane served no
credential route at all, so the assertion was measuring nothing. Fixed by adding
the three write endpoints to the mock plane and asserting the *success* wording.

**The resume test never stored anything, and asserted only that some step
rendered.** Fixed by parking the first context on a step the deployment does not
imply, storing a credential, and asserting the reopened context lands on the
derived step rather than on either step the first context visited.
