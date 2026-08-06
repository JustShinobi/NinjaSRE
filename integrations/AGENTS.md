# integrations/ — one package per vendor

**Tier 2.** May import: `core`, `platform`, `config`. Must never import: `capabilities`, `gateway`, `surfaces`.

Per-vendor configuration normalisation, credential schema, verifier, and API
client. One package per vendor, and roughly 85 of them by the end of wave 6.

## Conventions

- **Never import `capabilities`.** An integration stays reusable below the agent
  layer; the moment it reaches up, it stops being a client and becomes a tool.
- **A client never holds a credential**, and cannot: `IntegrationClient` has no
  constructor parameter for one. It carries a `RequestContext` — an
  organisation, a team, and a capability name, all safe in a prompt — and the
  proxy injects the secret at the network edge (Article IV).
- **No module here reads the process environment.** `make check-credentials`
  fails on any `os.environ` or `getenv` in this package, not only on a
  credential-shaped one: configuration comes from the hierarchy and credentials
  come from the proxy, so a lookup here is one or the other in the wrong place.
- Every integration ships the same seven artefacts — config, credential schema,
  verifier, client, typed tools, methodology skill, docs — and at least one
  synthetic scenario. Feature 024 defines the anatomy; feature 025 fills it in.
- Contract tests cover every client.

## The descriptor, and why there is no registry to edit

Every vendor package exposes a `DESCRIPTOR`: its credential schema, its
injection rule, its verifier, its client class, and which row of the vendor-SDK
table it sits on. `integrations/registry.py` finds them by walking the package
tree, so adding a vendor is one package and no edit anywhere else — the property
that has to hold for a catalogue of eighty-five to be addable one at a time.

A contract suite walks the same tree and asserts, per integration, that the
descriptor exists, that the client sits on `IntegrationClient`, that the rule
declares hosts and injections, and that every field an injection reads is one
the schema declares. An integration that forgets fails the day it lands.

Two things in the descriptor deserve care:

- **`InjectionRule.hosts` is the egress allow-list.** One tuple, not two,
  because two would drift. Exact host names, no wildcards: `*.vendor.com` is one
  delegated zone away from permitting a host nobody approved.
- **`sdk_strategy` records a decision, not a preference.** A vendor SDK that
  loads its own credential is replaced, not accommodated. `docs/integrations.md`
  is the table and the per-vendor rationale.

## Where things go

- Vendor API mechanics → `<vendor>/client.py`.
- Credential shape, hosts, and injection rule → `<vendor>/config.py`.
- The end-to-end credential check → `<vendor>/verifier.py`.
- The package's `DESCRIPTOR` → `<vendor>/__init__.py`.
- Anything that needs the secret at request-construction time — a signing
  scheme — is *not* here. It is a `RequestSigner` in
  `platform/credentials/proxy/signing/`, because signing requires the key.
- The agent-callable wrapper is *not* here — it is a tool in `capabilities/`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `integrations/`.
