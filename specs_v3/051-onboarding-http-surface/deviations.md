# Deviations — 051 The onboarding HTTP surface

Every place the implementation differs from `spec.md`, `plan.md` or `tasks.md`,
and why. Recorded as they happened rather than reconstructed afterwards. Not
committed — this whole directory is gitignored.

---

## 1. `credential.write` already existed, and so did its grant

**Planned.** T-002: "Implementar: `Permission.CREDENTIAL_WRITE`, concessão de
papel owner".

**Done.** Neither. `Permission.CREDENTIAL_WRITE` has been in
`platform/identity/permissions.py` since the identity feature, in the
`operator` increment — and because the roles nest strictly, `admin` and `owner`
hold it too. The only new thing is the route row that demands it.

**Why it matters rather than being a footnote.** The plan's reasoning for a
*new* permission was that "quem pode ajustar um limiar não é automaticamente
quem pode trocar o token de API" — and that separation is already a fact of the
catalogue. What this feature adds is the first route that actually depends on
it. `tests/security/test_onboarding_route_permissions.py::test_the_credential_write_demands_credential_write`
is the assertion; `tests/unit/gateway/http/test_onboarding_routes.py::test_credential_write_is_distinct_from_config_write`
records why the two must not be collapsed later.

<!-- proof: tests/security/test_onboarding_route_permissions.py::test_the_credential_write_demands_credential_write -->

---

## 2. `CredentialFieldSpec` moved to `platform/credentials/`, not `core/llm/`

**Planned.** "`CredentialFieldSpec` (atualmente `surfaces/cli/models`) se move
com ele" — that is, into `core/llm/onboarding/`.

**Done.** `platform/credentials/fields.py`. The onboarding package imports it
from there, as do `surfaces/cli/` and the gateway.

**Why.** The type describes one field of *any* credential — Datadog's
application key, a Kubernetes kubeconfig — and only incidentally a provider's.
Under `core/llm/onboarding/` the CLI's integration wizard, which has nothing to
do with models, would import its prompt shape from the LLM package. Both are
tier 3 and both are importable by the two surfaces, so the tier argument the
plan makes is satisfied either way; what differs is which package owns the
concept. `platform/credentials/` already owns `CredentialSchema`, and this is
the rendering half of the same fact — the module docstring says so in as many
words.

The plan's other half is kept exactly: no compatibility forwarding. The
definition is gone from `surfaces/cli/models.py`, its `__all__` entry with it,
and all six call sites were migrated in the same commit (Article VIII.4).

---

## 3. The descriptor package raises its own error, and the CLI translates it

**Planned.** Nothing said. `onboarding_for` raised
`surfaces.cli.errors.ConfigurationError`.

**Done.** `core.llm.onboarding.UnknownProviderError`, a `LookupError`, with
`surfaces/cli/wizard/flow.py::_chosen` translating it back into a
`ConfigurationError` at the surface.

**Why.** The old refusal reached *up* two tiers. Moving the package below the
surfaces without moving the error would have kept a tier-3 module importing
`surfaces/`, which `make check-imports` refuses — correctly. The translation
lives in the wizard because the exit code an operator's script branches on is a
CLI concern, and a traceback from a package they have never heard of is not an
answer. `UnknownProviderError` carries `known`, so the remedy still lists the
nine.

<!-- proof: tests/unit/surfaces/cli/wizard/test_onboarding_flow.py::test_an_unknown_provider_is_refused_with_the_ones_that_exist -->

---

## 4. The config route was not sealed because it was not composed

**Planned.** T-004: "Teste falhando: `PUT /v1/config/{node_id}` recusa um campo
que um schema de integração marca como secreto. Implemente a recusa na
validação do serviço de config se ausente."

**Done.** Both halves, and the second one was not where the plan expected.

The validation gap is real and is now closed: `ConfigValidator.secret_field_errors`
refuses any leaf whose *name* is a field an installed integration's schema marks
secret, wherever it appears in the document. The existing pass scans values for
secret *shapes*, and a key an operator invented for their self-hosted instance
matches nobody's shape.

The part worth recording is where the hole actually was. `IntegrationSettings`
is a closed schema — `api_key` written beside `name` was already a shape error —
so the reachable way round was its `settings` map, which is open because the
vendor defines what goes in it. And underneath that: `write_config` constructed
its own `ConfigService` **without the integration directory at all**, so no
cross-reference or credential-schema check ran on a write, while the read route
next to it reported both. The route now builds the service with the directory.

**What was deliberately not done.** The write is still not given the *capability
catalogue*, though `_service` supplies one and it would have been one word.
Adding it makes a write reject a capability reference that
`POST /{node_id}/preview` accepts — and a preview that does not predict its own
write breaks the property the preview exists for. That is a change the
configuration feature should make on both routes together, not a side effect of
sealing a credential path.

<!-- proof: tests/unit/gateway/http/test_onboarding_routes.py::test_the_config_route_refuses_a_field_an_integration_marks_secret -->
<!-- handoff: to=058-configuration-after-first-run what="validate config writes against the capability catalogue as well, on preview and write together" -->

---

## 5. Permissions for the provider routes, which the spec left open

**Planned.** "Toda rota nova tem linha na tabela de permissões de rota" — which
one, unstated.

**Done.** `GET /v1/providers` and `GET /v1/providers/{id}` take `config.read`;
`POST /v1/providers/{id}/verify` takes `integration.manage`.

**Why.** The two reads reveal no value — which providers this build supports,
which fields each needs, whether one holds a credential — and that is the same
class of fact `/v1/setup/checklist` serves. `config.read` is the narrowest
permission that fits, and `first_run_routes.py` already records the reasoning:
requiring more would put the provider list out of reach of the credential a
first run is holding. Verification is not a read. It makes a live call against
the operator's endpoint and spends their tokens, so it takes a manage
permission, is a `POST`, and is never reached by a listing.

<!-- proof: tests/unit/gateway/http/test_onboarding_routes.py::test_reading_the_provider_listing_never_verifies_anything -->

---

## 6. `verified` in the provider listing is always false, on purpose

**Planned.** "GET /v1/providers — os nove descritores mais estado por deployment
(configurado? verificado? qual modelo?)".

**Done.** The listing answers `configured` from the vault and `verified` as
false with a sentence saying nobody has checked. Only
`POST /v1/providers/{id}/verify` can return true.

**Why.** Nothing in this deployment records that a verification happened. There
are three ways to answer "verified?" in a listing and two of them are wrong: run
nine live verifications to render a page, which spends an operator's money every
time somebody opens the console; or report a stored credential as verified,
which is precisely the conflation the checklist exists to prevent. The third is
to say what is true — a key is stored and nothing has checked it — and let the
`POST` be the thing that checks.

Persisting a verification result would need a repository port, a Postgres
migration and a contract suite, which is a feature rather than a field.

<!-- proof: tests/unit/gateway/http/test_onboarding_routes.py::test_nothing_in_the_listing_claims_a_verification_nobody_ran -->
<!-- handoff: to=052-first-run-in-the-console what="decide whether a verification outcome is worth persisting, or whether the console verifies on demand" -->

---

## 7. Verification is composed, and the default does not read the vault

**This is the one genuinely unfinished thing in the feature, and it is a
composition gap rather than a missing route.**

**Planned.** "`POST /v1/providers/{id}/verify` — uma verificação ponta a ponta
real. Isto é `LocalServices.check_provider` alcançado por HTTP; faz chamadas ao
vivo."

**Done.** The route is real and makes a real call. `GatewayState.model_verifier`
is supplied at composition; without one the route falls back to
`core.llm.verification.verify_model(provider_id=...)`, which is the same
end-to-end preflight `make preflight` runs.

**What is unfinished.** That fallback resolves provider credentials the way
`core/llm` resolves them today, which is `EnvironmentCredentialResolver`. A key
written through `PUT /v1/integrations/anthropic/credential` goes to the vault,
and the vault has no `reveal` outside `platform/credentials/proxy/` — by design,
and this feature is not the one to weaken it. So on a *default* composition, a
provider key written over HTTP and then verified reports "the credential does
not resolve".

Closing it properly means the model call going through the credential proxy,
which injects the secret at the network edge. That is what the proxy is for and
it is a composition-root job: only the composition root knows whether this
process reaches its models through the proxy or through the environment. The
seam is in place and typed, and a deployment that wires the proxy supplies its
verifier and the route is correct.

**The same gap is item 2's, not only this route's.** Every model call an
investigation makes resolves the same way, so a provider key written by the new
route is not yet what an investigation reads either. Deviation 14 states that
against item 2's own wording; one handoff closes both, and it is the one below.

**What this means for the definition of done.** Item 1 —
`ninjasre --endpoint <url> --token <t> onboard` completing with a verified
provider — is met at the gate, against the real application, the real vault, the
real permission table and the real client, with the model call composed. It has
*not* been run manually against a validation container: there is none in this
repository, and the plan's "registrado em deviations com a transcrição" cannot
be honoured by inventing one. Both halves of that are stated here rather than
implied by a green suite.

<!-- proof: tests/contract/cli/test_onboarding_against_a_deployment.py::test_the_guided_first_run_completes_against_a_remote_deployment -->
<!-- handoff: to=052-first-run-in-the-console what="compose the gateway's model verifier through the credential proxy so a vault-written provider key verifies on a default deployment" -->

---

## 8. One credential route for integrations and providers, via a schema bridge

**Planned.** "Credenciais de provider pegam a rota do Escopo A com o id de
provider como o nome da integração."

**Done.** That, and the piece the plan did not name: a provider is not in
`integrations.registry.discover()`, so the route had nothing to validate
against. `core.llm.onboarding.credential_schema_for` turns a descriptor's
fields into a `CredentialSchema`, and `gateway/http/credential_schemas.py`
resolves a name through the integration registry first and the provider
descriptors second.

`POST /v1/integrations/{name}/verify` needed the same bridge and now has it —
the guided run stores a provider key and immediately verifies it, and a verify
that only knew about vendor packages refused the second half of its own flow.

No pattern is imposed on a provider's key. A vendor's key format changes without
notice and a nearly-right pattern refuses the deployment already using the newer
one, with no override.

<!-- proof: tests/unit/gateway/http/test_onboarding_routes.py::test_a_provider_credential_is_written_through_the_integration_route -->

---

## 9. An organisation-scoped caller could not write a credential at all

**Planned.** Nothing. Found while writing T-013.

**Done.** `_team_of` in `gateway/http/routes/integrations.py`. A credential
handle needs a team and the vault spells the organisation-wide owner as a
literal `-`; an organisation-scoped token has `team_node_id == ""`, which
`CredentialHandle` refuses. Both handlers now fall back to the organisation-wide
handle, which is the one every team already inherits from.

**Why it is here rather than silent.** The pre-existing `verify_integration`
carried the same defect for the same reason, and it is now fixed too — a
`MalformedHandle` surfaced as a sanitised 500, which reads as "the deployment is
broken" rather than "this token has no team".

---

## 10. The checklist reads the vault across teams, and takes its integrations

**Planned.** Escopo D: distinguish three provider states, plus per-integration
configured/verified/declared "de `catalogue(health=ledger)`, que
`gateway/http/routes/integrations.py` já lê".

**Done.** `build_checklist` gained `integrations` and `verified_integrations`
parameters and reads the vault itself; `gateway/http/routes/first_run.py` reads
the catalogue and the health ledger and passes both in.

**Two decisions inside that.**

The catalogue is read in the *route*, not in `build_checklist`. `platform/` is
tier 3 and `integrations/` is tier 2 — reaching up is the boundary
`make check-imports` exists to hold, and there is no way to phrase it that is
not a violation.

The vault read is `Vault.list(scope)` — every handle in the organisation —
rather than a per-name lookup at the organisation-wide handle. A credential
written by a team-scoped operator lives under `anthropic/payments`, and a read
scoped to the organisation handle would report "no provider" on a deployment
that has one. The question a first run asks is "has anybody configured this
here", and that is the read that answers it.

**Vocabulary.** One set of three words — `absent`, `configured`, `verified` — in
`config/constants/first_run.py`, used for the provider step and for each
integration. The spec says "apenas declaradas" for the integration case; that is
`absent`, and the list only ever contains integrations the deployment declares,
so "not in the list" and "in the list holding nothing" stay different facts. Two
words for one idea would have been worse than one word explained.

An integration is `verified` when the health ledger says a live run reached it.
That is the only record of a vendor actually answering that exists, and it is
the right one: it is what "verified" means.

<!-- proof: tests/unit/platform/startup/test_checklist.py::test_the_three_provider_states_are_distinguishable_in_the_record -->

---

## 11. The contract harness was hiding every refusal the API wrote

**Planned.** Nothing.

**Done.** `tests/contract/cli/test_remote_client_speaks_the_api.py` now hands
`urllib.error.HTTPError` the response body as its file object, which is what
`urllib` does over a socket.

**Why.** Without it `RemoteClient._failure_detail` has nothing to read, so every
refusal in that suite arrived as a bare `"… answered with status 400"` and the
sentence the deployment wrote for the operator was invisible to the test. The
first assertion that needed it — a schema violation naming `app_key` — failed
against a client that was working correctly. A harness that cannot see the
message is a harness that cannot assert the message is safe.

---

## 12. `credential_fields` answers empty rather than raising for an unknown vendor

**Planned.** T-010 says only that the refusal is deleted.

**Done.** Two sources — the node's integration schemas, then the provider
descriptors — and `()` for a name neither answers to.

**Why.** `surfaces/cli/wizard/integrations.setup` already turns an empty field
list into `"{integration!r} declares no credential fields"` with a remedy about
the package not being installed. That is a better sentence than anything the
transport layer could write about a name it was handed, and raising here would
have replaced it with a 404.

---

## 13. Provider assertions moved out of the wizard's suite

**Planned.** T-006: "Suite Wizard fica verde."

**Done.** Green, and four of its tests are now in
`tests/unit/core/llm/test_provider_onboarding.py` instead — the ones asserting
what the descriptors *declare*, which is no longer the wizard's business. The
wizard's file keeps what is about the wizard: that all nine are offered, that
the key is asked for without echo, that the flow ends in a verification.

Nothing was dropped. The new file adds two assertions the old one did not make:
that every onboarded provider is one the model registry can actually build, and
that a descriptor is frozen.

---

## 14. "Usable by an investigation" is true for an integration and not yet for a provider

**Planned.** Definition of done item 2: "Uma credencial armazenada pela rota nova
é usável por uma investigação **e** greppable em lugar algum."

The second half is proven over everything a whole guided run produced (see the
appendix). The first half is two different claims wearing one sentence, and only
one of them holds today. A done-auditor pass caught the appendix quietly
narrowing item 2 to the sweep; this entry is the correction.

**An integration credential is usable, and it is now proven.**
`tests/security/test_credential_write_never_leaks.py::test_what_the_route_wrote_is_what_the_proxy_resolves`
writes through the route and then resolves through
`platform.credentials.proxy.resolution.CredentialResolver` — the single
sanctioned reader, and the component that injects the secret at the network edge
for every authenticated call an investigation makes. It comes back under the
handle the route wrote, at the version the response reported, with the values
that went in. Its neighbour proves a rotation is what resolves next, with no
restart and no cache to clear. That is the whole of what "usable" means for a
vendor credential: the proxy is the only thing entitled to use one.

**A provider credential is not, and the reason is deviation 7.** `core/llm`
resolves provider credentials through `EnvironmentCredentialResolver`, not
through the vault, so a provider key written by this route is not yet what an
investigation's model client reads. This is the *same* composition gap deviation
7 records for `POST /v1/providers/{id}/verify`, and it was wrong of me to record
it only there: it applies to any model call under a default composition, not
just to verification. One handoff closes both.

**What this means for the definition of done.** Item 2 is met for an
integration credential and unmet for a provider credential, and the gate now
says which is which rather than leaving the sentence to be read charitably.

<!-- proof: tests/security/test_credential_write_never_leaks.py::test_what_the_route_wrote_is_what_the_proxy_resolves -->

---

## 15. The `--endpoint` refusal set is down to two

`RemoteClient` refused seven things by name. Five are implemented; `cost_of_runs`
and `spend` remain, because there is genuinely no cost route — the plan lists
them as out of scope and they stay refused rather than answered from defaults.
The parametrised refusal test in the contract suite shrank to those two, and the
"a refusal never carries what was asked" assertion moved onto one of them.

---

## Appendix — where each acceptance item is proven

| Item | Test |
|---|---|
| 1 — `onboard` completes against a remote deployment | `tests/contract/cli/test_onboarding_against_a_deployment.py::test_the_guided_first_run_completes_against_a_remote_deployment` (see deviation 7 for the manual half) |
| 2 — a written credential is usable by an investigation… | `tests/security/test_credential_write_never_leaks.py::test_what_the_route_wrote_is_what_the_proxy_resolves` for an integration credential. **Unmet for a provider credential** — see deviation 14 |
| 2 — …and greppable nowhere | `tests/contract/cli/test_onboarding_against_a_deployment.py::test_the_key_entered_at_the_prompt_is_in_the_vault_and_nowhere_else` over a whole guided run, and `tests/security/test_credential_write_never_leaks.py` over the route alone |
| 3 — `doctor` returns a report | `tests/contract/cli/test_remote_client_speaks_the_api.py::test_doctor_returns_a_report_rather_than_a_refusal` |
| 4 — three distinguishable deployment states | `tests/unit/platform/startup/test_checklist.py::test_the_three_provider_states_are_distinguishable_in_the_record` |
| 5 — every new route has a permission row | `tests/security/test_onboarding_route_permissions.py`, whose `ONBOARDING_ROUTES` import fails the build if a row is dropped; the wiring-time refusal is `tests/security/test_route_permissions.py::test_an_undeclared_route_cannot_obtain_a_guard` |
