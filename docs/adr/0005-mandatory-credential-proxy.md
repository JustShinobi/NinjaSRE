# ADR 0005 — Credential proxy mandatory in every profile

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article IV

## Context

An SRE agent must authenticate to a large number of production systems. How those
credentials reach the call is a security decision with a wide blast radius.

**The pipeline design** resolves credentials into the process: a keyring-backed secret store,
environment variables, and per-integration credential objects passed to clients.
The agent process holds real secrets.

**The memory design** introduces a credential proxy for its production sandbox mode. Skill
scripts receive only `TENANT_ID` and `TEAM_ID`; a proxy at the
network boundary resolves and injects the actual API key. The skill documentation
states plainly: *"Credentials are injected automatically by a proxy layer. Do NOT
check for `DATADOG_API_KEY` — they won't be visible to you."*

The risk with in-process credentials is not primarily theft. It is that an LLM
agent with filesystem and shell access can read an environment variable and then
place it somewhere it does not belong: a prompt sent to a third-party model
provider, a log line, an investigation report posted to Slack, a trace persisted
to the database, or a stack trace surfaced to a user. Every one of those paths has
produced a real incident in some system.

## Decision

**The credential proxy is mandatory in every deployment profile — development,
standard, and enterprise.**

1. The agent context never holds a credential: not in environment, prompt, tool
   arguments, filesystem, or trace.
2. Integration clients issue requests carrying a tenant/team-scoped handle. The
   proxy resolves the handle against the encrypted vault and injects the real
   secret at the network edge.
3. Non-secret configuration (region, site, base URL, cluster name) may be visible.
4. `integrations/_base/client.py` is the only sanctioned way to make an
   authenticated external call. A contract test fails any client that reads a
   secret from the environment.

## Rationale

**Removing reach removes the class.** Redaction, masking, and output filtering are
all detection-based — they need to recognise the secret to remove it. If the agent
never receives the secret, no detector needs to be correct.

**Multi-tenancy demands it.** With org → team hierarchies and per-team
credentials, in-process resolution means one process holds every tenant's secrets.
A prompt-injection payload in a log line the agent reads becomes a cross-tenant
credential exfiltration path. The proxy scopes resolution to the requesting
tenant.

**Development parity prevents drift.** The memory design treats the proxy as a production
mode, so its default path lets skills read real keys. Any code written and tested
that way will read environment variables, and the difference only surfaces in
production. Making the proxy mandatory everywhere means the constraint is enforced
by the code contributors run every day.

**It is a precondition for sandboxing.** With no credential in the agent context,
sandbox profiles are about resource and egress control, not secret containment —
which makes the lighter profiles genuinely safe rather than merely convenient.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Credentials in-process, redaction at boundaries (the pipeline design) | Detection-based; every path from agent to output must be covered forever, and one miss is a leaked production key |
| Proxy in production only (the memory design) | Development code diverges from production behaviour; the invariant is not exercised by the code people actually write |
| Proxy optional per integration | Creates a two-tier security model where the weakest integration defines the system's guarantee |

## Consequences

**Positive**

- Credential leakage into prompts, logs, traces, or reports becomes structurally
  impossible rather than filtered
- Per-tenant scoping is enforced at the network edge
- Every deployment profile carries the same guarantee
- Credential rotation happens in the vault with no agent restart

**Negative**

- Every integration client must be written against the proxy base — no vendor SDK
  can be used with its default credential handling
- The proxy is a single point of failure on the request path and must be highly
  available
- Local development requires the proxy running, adding a step
- Vendor SDKs that sign requests client-side (AWS SigV4) need special handling

**Mitigations**

- The `dev` profile runs the proxy in-process as a lightweight local component;
  no extra container
- SigV4 and other client-side signing schemes are handled by proxy-side signing:
  the proxy holds the credential and signs the outbound request
- `integrations/_base/client.py` makes the correct path the easiest path
- A CI check greps integration packages for direct secret-env access and fails
- Proxy failure produces an explicit, actionable capability error — never a silent
  fallback to unauthenticated or direct-credential mode
