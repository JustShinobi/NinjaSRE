# integrations/ — one package per vendor

**Tier 2.** May import: `core`, `platform`, `config`. Must never import: `capabilities`, `gateway`, `surfaces`.

Per-vendor configuration normalisation, credential schema, verifier, and API
client. One package per vendor, and roughly 85 of them by the end of wave 6.

## Conventions

- **Never import `capabilities`.** An integration stays reusable below the agent
  layer; the moment it reaches up, it stops being a client and becomes a tool.
- A client never holds a credential. It carries a tenant-and-team-scoped handle
  and the proxy injects the secret at the network edge (Article IV).
- Every integration ships the same seven artefacts — config, credential schema,
  verifier, client, typed tools, methodology skill, docs — and at least one
  synthetic scenario. Feature 024 defines the anatomy; feature 025 fills it in.
- Contract tests cover every client.

## Where things go

- Vendor API mechanics → `<vendor>/client.py`.
- Credential shape and health check → `<vendor>/config.py` and `<vendor>/verifier.py`.
- The agent-callable wrapper is *not* here — it is a tool in `capabilities/`.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `integrations/`.
