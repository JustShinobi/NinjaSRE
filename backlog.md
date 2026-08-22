# Backlog

Work this deployment has shown it needs, written down where the next person
looking at it will find it.

---

## A deployment should produce its own first administrator

**What happens today.** A fresh deployment comes up with no way in. The console
serves its sign-in form, the form asks for a name and a passphrase, and it
refuses every combination — including the right one, because there is no right
one. `LocalAccount.from_environment` returns `None` unless
`NINJASRE_LOCAL_ACCOUNT_PASSWORD_HASH` is already set, and nothing in the
deployment path sets it.

Getting in for the first time currently means: read the source to learn the
variable exists, find `platform.identity.local_accounts.hash_local_password`,
run it against a passphrase somebody chooses, put the result in a Secret by
hand, and wire that Secret into two Deployments. Staging needed exactly that
before anybody could open it, and none of those steps is discoverable from the
screen that refuses you.

**Why it is not simply a missing default.** The current behaviour is
deliberate, and the reasoning in `local_accounts.py` is sound: a way in that
nobody asked for is a way in, a deployment with an identity provider should not
acquire a second door by installing a release, and the passphrase this project
ships with is refused outside a declared demonstration so that a default
documented as "change this" cannot reach production. Any fix has to keep all
three of those true. "Ship a default admin password" is not the answer.

**What other applications do**, and what is worth taking from each:

- **A first-run screen.** The deployment comes up with no account and the first
  visitor is shown a form that creates one, which then stops being reachable.
  GitLab, Grafana on first boot, Sonarr and most self-hosted software work this
  way. It needs the window to close for good — a "create the first admin" route
  that stays open is an open door — and it needs to survive several replicas
  racing for it.
- **A token printed once at boot.** The deployment writes a single-use
  credential to its own log or a file, and the operator reads it out and
  exchanges it. Jupyter, Portainer and Argo CD do this. Most of the machinery
  is already here: `bring_up` issues a bootstrap credential, writes it to the
  host, and `POST /v1/setup/durable-credential` exchanges it for a durable one.
  What is missing is that the exchange produces an API token rather than
  something the console's sign-in form accepts, so an operator ends up holding
  a credential the screen in front of them cannot use.
- **A command the operator runs.** `django-admin createsuperuser`, and the same
  shape in Rails and Laravel. The CLI is already in every image, so this may be
  the smallest honest step: `ninjasre setup admin --username …`, prompting for
  the passphrase without echoing it, hashing it and storing it — which also
  gives an answer for rotating it and for a second administrator.

**Worth deciding along the way.** The exchange path and the sign-in form
currently end in different places, and that is the seam this falls through: one
produces a bearer token, the other wants a name and a passphrase. Whatever is
built should make those one flow, so that "I have a credential" and "I can sign
in" stop being separate facts.

**How it should be judged.** A person who has just deployed this, and has read
nothing, can sign in. Nothing they had to do was learned by reading source.
Whatever door it opens is closed behind them, and a deployment that already has
an identity provider gains no second one.

---

## An integration cannot be told where it is

**What happens today.** The catalogue asks for a secret and never for an
address. Every self-hosted vendor's `SCHEMA` declares credential fields only,
and the client resolves its base URL from a `RegionMap` constant compiled into
the package — `alertmanager.example.com`, `prometheus.example.com`,
`grafana.example.com`. An operator whose Alertmanager answers on
`http://10.20.20.36:9093` has nowhere to say so. The credential is stored, the
verifier reports it stored, and every call the integration makes goes to a
documentation placeholder.

**The wire was designed and never connected.**
`platform/config_service/schema/integrations.py` declares `base_url` on
`IntegrationSettings`, described as "the address of your own instance, for a
vendor you host yourself". Each self-hosted schema exposes `rule_for(*hosts)`
and `regions_for(**endpoints)`, whose docstrings say the allow-list is a
declaration the *operator* makes. Nothing outside `integrations/` and the test
suite calls either, and nothing reads `base_url`. Three separate mechanisms for
one fact, none of them reachable from a running deployment.

**The required field is the wrong one for the common case.** Alertmanager and
Prometheus ship no authentication — both packages' own `docs.md` say so — and a
homelab runs them bare on a private address. `secret("token", …)` is required,
so those two cannot be connected at all. `InjectionRule.credential_optional`
exists for exactly this ("a self-hosted vendor run with auth turned off, most
often") and no integration sets it.

**Two different secrets share one word.** The token the catalogue stores is
*outbound*: it authenticates NinjaSRE to the vendor. The token that makes alerts
arrive is a delivery token, issued on the alert-intake screen, presented by the
alert router when it posts to `/webhooks/alertmanager`. Both are called "token".
They live on different screens, and only one of the two screens links to the
other. An operator who stores the outbound token and waits for alerts waits
forever, and nothing on the screen tells them why.

**The screen has the room and nobody filled it.** `CredentialFieldView` already
serves `label`, `min_scope` and `guide_url`; the console already renders a
minimum-permission hint and a step-by-step guide link from them. All three are
empty in all fifteen packages, so both are dead code. `IntegrationPanel` never
passes `whereToGetIt`, so that string is unreachable too. Each package carries a
`docs.md` answering most of what an operator asks — served by no route. The
i18n keys written to say "point your alert router here" are referenced by no
component.

**What other applications do**, and what is worth taking from each:

- **Address and credential in one form.** Grafana's data-source screen, Argo
  CD's repository screen, and every self-hosted tool that integrates with
  another self-hosted tool ask for the URL first and the secret second, on one
  page, and test both together. The URL is not a secret and does not belong in a
  vault; it does belong beside the field that cannot work without it.
- **Naming the direction.** Sentry, PagerDuty and Grafana all distinguish "we
  call you" from "you call us" in the setup UI itself, because the credential is
  different in each direction and an operator who confuses them gets silence
  rather than an error.
- **Testing what was entered, not what was declared.** A connection test that
  reaches the address the operator typed is the only test that answers the
  question they are asking. Testing against a compiled-in host proves the vault
  works.

**How it should be judged.** Somebody with an Alertmanager on a private address
and no reverse proxy in front of it can connect it from the console, without
reading source, and see a test that actually reached it. The screen says which
direction the traffic goes, and when the integration also receives, it says what
to do next and links to where that is done.

---

## Four seams between what is configured and what runs

Found while tracing the integration flow. Each is larger than the catalogue
work above and none of them is a copy problem.

- **The production investigator does not narrow tools by configured
  integrations.** `gateway/runtime/investigator.py` says so in its own
  docstring: a capability the deployment holds no credential for is still
  offered, and reports itself unavailable when called. The ranker scores against
  what the alert says, not against what the team connected.
- **`TeamCatalogueResolver` is never instantiated.** It is the only resolver
  that reads a team's configured integrations. Its sole mentions are a docstring
  example, a re-export, and an `__all__` entry.
- **The six-stage pipeline has no production caller.** `build_pipeline` is
  invoked only from tests and harnesses; the serving path builds a `ReActLoop`
  directly. `ResolveIntegrationsStage` — including the well-built
  zero-integration outcome that names which integration to connect and how many
  capabilities it would unlock — never runs for a real alert.
- **The investigator's model key comes from the environment, not the vault.**
  `get_llm()` resolves through the environment-backed stand-in, while the
  console's verify path reads the vault first. An operator who pastes a key into
  first-run and sees it verified has verified a key the investigator will not
  use.

---

## "Test again" never reaches the vendor

**What happens today.** The catalogue offers "Save and test" and "Test again",
and neither makes a vendor call. `POST /v1/integrations/{name}/verify` answers a
cheaper question — is a credential present, current and decryptable — and
`POST /v1/integrations/{name}/verify/report`, the one that would reach the
vendor, answers 404: *"no deep verifier is composed"*. `GatewayState.deep_verifier`
defaults to `None` and nothing in any composition root sets it, so that 404 is
every deployment's answer.

The machinery underneath is real and complete. Every one of the fifteen packages
ships a verifier; `integrations/_verification/framework.py` has a runner that
probes connectivity and then each declared permission, and reports which were
granted; `python -m tools.verify_integrations --live` drives exactly that from
CI. What is missing is the three lines that hand the runner the transport and
context the gateway already holds.

**Why it is not simply those three lines.** A verifier builds its own client —
`self._client(transport, context)` — rather than going through
`IntegrationAccess.client(...)`, which is what applies the address an operator
configured. Composed as it stands, "Test again" would faithfully test
`alertmanager.example.com` and report that the placeholder is unreachable. The
verifier protocol has to carry the address too, which is a change to
`IntegrationVerifier.connect` and `.probe` and to fifteen implementations of
them.

**Why it matters more than it looks.** "Stored" and "works" are different facts,
and this repository is careful about the difference everywhere else: the
catalogue reports `unknown` rather than `healthy` for an integration nothing has
run against, and a rotation forgets the previous verdict rather than carrying it
forward. Then the one control that would turn `unknown` into a measurement is
inert, so every integration an operator connects stays `unknown` for ever — and
`unknown` is exactly what they connected it to find out.

**How it should be judged.** An operator presses "Test again" on an integration
they have just pointed at their own instance, and gets back what that instance
said: reachable or not, and which of the declared permissions the credential
actually has. Nothing in the answer is about a placeholder host.
