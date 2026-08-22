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

## The screen has room the packages have not filled

The larger half of this entry is done: a self-hosted vendor now declares an
address, the write splits by field kind, the three that ship no authentication
are `credential_optional`, the panel says which way the traffic goes, and "Test
again" reaches the operator's own instance and reports what it said. What is
left is the guidance around the fields.

`CredentialFieldView` serves `label`, `min_scope` and `guide_url`, and the
console renders a minimum-permission hint and a step-by-step link from the last
two. Every field now has a label. Twenty-eight of forty have no `min_scope` and
twenty-nine no `guide_url`, so for most fields both renderings are still dead.
`IntegrationPanel` never passes `whereToGetIt`, which the first-run screen does
pass, so the same string is reachable on one screen and not the other. Each
package carries a `docs.md` answering most of what an operator asks, and no
route serves it.

None of this stops an integration working. All of it is the difference between
a field somebody can fill in and a field somebody has to research.

**How it should be judged.** An operator who has never seen the vendor's console
can tell, from this screen, what to create there and what to tick — without
opening a browser tab to find out.

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

## A vendor with a self-signed certificate cannot be connected

**What happens today.** Proxmox is pointed at, its API token is stored, the
catalogue reports it configured — and every call fails with *"Neither the
credential proxy nor any configured Proxmox node answered"*. The reason is one
line up from there: the proxy will not accept the certificate. Proxmox ships a
self-signed one and generates a new one on install, which is not an unusual
deployment. It is the default one.

**The mechanism exists and is not wired.** `integrations/proxmox/certificates.py`
has `CertificateTrust` with three ways to say what this deployment accepts — a
pinned fingerprint, a supplied PEM, and an explicit `unverified(reason=…,
accepted_by=…)` that makes accepting one a recorded decision rather than a flag.
`integrations/proxmox/docs.md` documents all three. No schema field offers any
of them, no configuration path carries one, and `ProxmoxClient` takes
`DEFAULT_TRUST` because nothing ever passes anything else.

**Why it is not one more schema field.** The client is not what opens the
connection. Every vendor call goes through the credential proxy, and the TLS
handshake happens on its egress side — so a trust decision expressed on the
client reaches nothing. Whatever carries it has to reach `platform/credentials/proxy`,
which is the one place in this codebase where a deliberate weakening of
certificate verification would live. That makes it a change to the security
boundary, and it deserves to be designed as one: who may accept an unverified
certificate, whether the acceptance is per vendor or per address, and what the
audit trail records when somebody does.

**How it should be judged.** An operator with an ordinary Proxmox install
connects it, and either the deployment trusts the certificate they gave it or it
refuses with a sentence naming the certificate — never with "no node answered",
which sends them to check a network that is fine.

---

## The alert router had no way to reach this deployment, twice over

**What happened.** Adding a webhook receiver to Alertmanager did not make the
inbound loop work, and the two reasons are worth writing down because neither
shows up as a failure anywhere an operator would look.

The apply that renders the Alertmanager configuration asked Infisical for the
NinjaSRE listener token, and that key had no arm in the mapping the fetch
switches on — so every apply died naming a secret it had just been told to
fetch. It is fixed, but the shape recurs: a resolver and a mapping in two places
that have to agree, with no check that they do.

Then the router could not resolve the name it was given. The container's
configured nameserver had stopped existing; every `.lan.kyo.ninja` name returned
nothing, and the receiver posted to a host that did not resolve. The
receiver that has worked for years next to it uses a bare IP, which is why the
gap was invisible.

**What is still true.** The other two monitoring containers point at the same
dead resolver. They work because everything reaches them by address. The first
one that is given a name will fail the same way.

---

## Two seams the deep verify opened rather than closed

**A team's credential verifies green and is invisible to an investigation.**
The deep verify now resolves as the team of the caller, which is what makes a
team-scoped credential test correctly. Vendor *tools* still run under the
organisation-wide binding `compose_integration_access` sets. So an operator can
connect an integration under their team, see it verified against the real
vendor, and have every investigation report that same integration unavailable.
The two should resolve the same way, and deciding which way is the work.

**A credential against a plain-HTTP address is now refused, visibly.**
`refuse_credential_in_clear` has always refused to send a credential over an
unencrypted connection; until an operator could enter an address, nothing
reached it. Now they can, and pointing a vendor at `http://…` with a token
stored is met with a refusal. That is the correct behaviour and the message is
the vendor-call one rather than a sentence about the scheme. It should say what
happened and what to do: use the TLS address, or store no credential.

---

## A deployment cannot hold two service accounts

Creating a second principal with no email address fails with a raw
`asyncpg.exceptions.UniqueViolationError` on `ix_users_email`: the folded-email
index treats two empty strings as a collision. `User` declares `email` as an
ordinary string with no hint that empty is reserved, and the first service
account a deployment creates takes it. Nothing in the type, the port or the
message says so — the operator gets a Postgres constraint name.

---

## The Infisical operator in the cluster cannot authenticate

Every `InfisicalSecret` in the cluster is failing to sync, and has been:

> authentication failed for strategy [KUBERNETES_AUTH_MACHINE_IDENTITY] …
> Failed to communicate with Kubernetes API server at
> https://k3s-api.lan.kyo.ninja:6443: canceled

Secrets already materialised survive, because the managed Kubernetes secret is
owned rather than re-created, so nothing looks broken until something needs a
new one or a rotated one. Not this project's defect, but it is the reason a
credential for this deployment is written into its own vault by hand rather than
delivered by the operator that exists for exactly that.

---

## The model gateway needs a key that exists nowhere

`OLLAMA_BASE_URL` now points at the gateway that is actually there, and the
route restricted to this cluster's nodes reaches it. It answers 401: the gateway
requires an API key, and it requires one from its own host as well, so there is
no source-address exemption to lean on. No such key is in the vault, and the
deployment beside this one that uses the same gateway does not carry one either.
Somebody has to issue one in the gateway's own console and store it; until then
the only model provider this deployment can use is the one with a key.
