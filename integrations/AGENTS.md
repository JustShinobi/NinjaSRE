# integrations/ — one package per vendor

**Tier 2.** May import: `core`, `platform`, `config`. Must never import: `capabilities`, `gateway`, `surfaces`.

Per-vendor credential and connection schema, verifier, API client, and typed
tools. One package per vendor — exactly the vendors an environment exists to
validate end to end, read from the discovered catalogue rather than counted
here.

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
- **A package whose name starts with an underscore is framework, not a vendor.**
  `_base`, `_verification`, and `_catalogue`. Discovery skips them, and that is
  where the convention becomes enforcement.
- Contract tests cover every client, and they are one suite over the discovered
  catalogue rather than one file per vendor.

## The seven artefacts

Every integration ships all seven, and `make verify` fails naming both the
integration and the artefact when one is missing.

| # | Artefact | Where |
|---|---|---|
| 1 | `schema.py` — credential fields, hosts, regions, injection rule | `<vendor>/` |
| 2 | `verifier.py` — connectivity and one probe per permission | `<vendor>/` |
| 3 | `client.py` — the API, on `IntegrationClient` | `<vendor>/` |
| 4 | `tools/` — the typed capabilities the agent calls | `<vendor>/` |
| 5 | `SKILL.md` — the methodology | `capabilities/skills/<vendor>/` |
| 6 | `docs.md` — setup, permissions, limitations | `<vendor>/` |
| 7 | a synthetic scenario | `tests/synthetic/integration_scenarios/<vendor>.py` |

Start with the scaffold, which writes all seven and edits nothing:

```bash
uv run python tools/scaffold_integration.py <vendor> --domain <domain>
```

[`docs/integration-framework.md`](../docs/integration-framework.md) is the long
form: what the base client gives you, how verification reads a vendor's refusal,
and the two decisions the scaffold deliberately refuses to make.

## The two declarations, and why there is no registry to edit

Every vendor package exposes two objects, and discovery walks the tree for both.

**`DESCRIPTOR`** is the credential half: the schema, the injection rule, the
verifier, the client class, and which row of the vendor-SDK table it sits on.

**`PROFILE`** is the operational half: the category, a summary, the region map,
the permissions its capabilities need, and how each paginated endpoint asks for
the next page.

Adding a vendor is one package and no edit anywhere else — the property that has
to hold for a growing catalogue to be addable one package at a time.

Three things deserve care:

- **`InjectionRule.hosts` is the egress allow-list**, and it is the region map
  rather than a second tuple, because two would drift. Exact host names, no
  wildcards: `*.vendor.com` is one delegated zone away from permitting a host
  nobody approved.
- **`sdk_strategy` records a decision, not a preference.** A vendor SDK that
  loads its own credential is replaced, not accommodated.
  `docs/integrations.md` is the table and the per-vendor rationale.
- **A permission is probed, never assumed.** A guessed permission is worse than
  a missing one: verification reports success for a credential that cannot do
  the job, and the failure surfaces during an incident.

## Where things go

- Vendor API mechanics → `<vendor>/client.py`.
- Credential fields, hosts, regions, and the injection rule → `<vendor>/schema.py`.
- Connectivity and permission probes → `<vendor>/verifier.py`.
- The agent-callable capabilities → `<vendor>/tools/`.
- `DESCRIPTOR` and `PROFILE` → `<vendor>/__init__.py`.
- Reading a vendor's answer — a value several levels down, the record list, a
  cursor, an XML document, a column-and-row result, or counts grouped by one
  field → `_base/payload.py`. None of those belongs in a client: written per
  vendor they are index expressions, and an index expression on an error body
  that arrived with the same content type raises inside a capability, which
  ends the turn and takes the trace with it.
- A vendor the catalogue **cannot** reach → `_catalogue/gaps.py`, with the
  reason and what would change it. The parity check walks the packages that
  exist, so a vendor nobody wrote is a vendor nobody is told about; the
  omission has to be a declaration or the catalogue reports full parity while
  an operator discovers the absence by looking for it.
- Anything that needs the secret at request-construction time — a signing
  scheme — is *not* here. It is a `RequestSigner` in
  `platform/credentials/proxy/signing/`, because signing requires the key.

## Reading a vendor's refusal

Four answers, four different things to tell an operator, and three of them are
commonly collapsed into "permission denied":

- **403** — the permission is missing. Name it, and say what stops working.
- **404** — the call was *permitted*; the resource is not there. Probes name
  absent objects deliberately, because that is what makes them cheap.
- **401** — nothing was learned about the permission. It is unchecked, not
  denied.
- anything else — the check did not complete, and saying so beats reporting
  "granted" because no denial arrived.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `integrations/`.
