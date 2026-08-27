# Feature 007 — Credential Vault and Proxy

- **Wave:** 1 — Trust & Safety
- **Branch:** `feat/007-credential-vault-and-proxy`
- **Status:** Draft
- **Depends on:** 001, 006
- **Blocks:** 009, 013, 024, 025
- **ADRs:** [0005](../../docs/adr/0005-mandatory-credential-proxy.md)

## Summary

The mechanism that makes Constitution Article IV structurally true: the agent
never holds a credential. Integration clients issue requests carrying a
tenant/team-scoped handle; a proxy resolves it against an encrypted vault and
injects the real secret at the network edge. Mandatory in every deployment
profile, including local development.

## User scenarios

### Primary story

An engineer writes a new Datadog capability. They never see, configure, or handle
an API key. Their client calls the proxy with a service handle; the request
reaches Datadog authenticated. A prompt-injection payload in a log line the agent
reads cannot exfiltrate the key, because the key was never in reach.

### Acceptance scenarios

1. **Given** any capability executing, **when** its process environment,
   filesystem, prompt, tool arguments, and trace are inspected, **then** no
   credential value is present anywhere.
2. **Given** an integration client issuing a request, **when** it reaches the
   proxy, **then** the proxy resolves the credential for the requesting tenant and
   team and injects it into the outbound request.
3. **Given** a request whose tenant lacks the credential, **when** it reaches the
   proxy, **then** it is rejected with a structured, actionable error naming the
   missing integration — and no fallback to an unauthenticated call.
4. **Given** a credential rotated in the vault, **when** the next request runs,
   **then** it uses the new value with no restart.
5. **Given** an AWS SigV4-signed request, **when** it is issued, **then** the proxy
   performs the signing; the client never possesses the signing key.
6. **Given** the `dev` profile, **when** the platform starts, **then** the proxy
   runs in-process and the same invariant holds — no separate container required.
7. **Given** an integration client that reads a secret from the environment,
   **when** CI runs, **then** the check fails naming the module.
8. **Given** a proxy outage, **when** a capability executes, **then** it fails with
   a clear error and never falls back to direct credentials.
9. **Given** an audit query, **when** it runs, **then** every credential
   resolution is recorded with tenant, team, integration, capability, and outcome
   — without the value.

### Edge cases

- Two teams in the same org holding different credentials for the same vendor.
- A credential valid at request start expiring mid-request (OAuth, STS).
- A vendor requiring the secret in a URL path or query string rather than a header.
- A vendor SDK that constructs and signs requests internally.
- Streaming or long-lived connections (websocket, log tail) that outlive a token.
- A capability legitimately needing a non-secret value that looks like one.

## Requirements

### Functional

**Vault**

- **FR-001** Credentials MUST be stored encrypted at rest via `CredentialStore`
  (feature 006), scoped by org and team.
- **FR-002** The vault MUST support versioned credentials so rotation is
  non-destructive and rollback is possible.
- **FR-003** A credential value MUST NEVER be returned to any caller outside the
  proxy. The store's read API MUST expose metadata only — presence, type, version,
  last rotation, expiry.
- **FR-004** Credential schemas MUST be declared per integration (field names,
  types, required/optional, validation).
- **FR-005** Writing a credential MUST validate it against the integration's
  schema before persistence.

**Proxy**

- **FR-006** The proxy MUST be the only component that reads credential values.
- **FR-007** Requests MUST carry tenant and team context and an integration
  handle; the proxy resolves and injects.
- **FR-008** Injection MUST support: request headers, query parameters, path
  segments, request-body fields, basic auth, bearer tokens, and request signing
  (SigV4 and vendor equivalents).
- **FR-009** The proxy MUST enforce an egress allow-list per integration — a
  request to a host the integration does not declare MUST be rejected.
- **FR-010** The proxy MUST NOT provide a bypass, fallback, or direct-credential
  mode under any configuration.
- **FR-011** The proxy MUST run in-process in the `dev` profile and as a separate
  service in `standard` and `enterprise`, with identical behaviour.
- **FR-012** Credential resolution failure MUST produce a structured error naming
  the integration and the reason, surfaced to the agent as a capability result.
- **FR-013** The proxy MUST refresh short-lived credentials (OAuth, STS) before
  expiry and retry a request that failed on expiry exactly once.
- **FR-014** The proxy MUST apply per-tenant rate limiting and record it.

**Client contract**

- **FR-015** `integrations/_base/client.py` MUST be the only sanctioned path for
  an authenticated external call.
- **FR-016** The base client MUST provide: retry, pagination, timeout, rate-limit
  handling, structured errors, and proxy routing.
- **FR-017** A CI check MUST fail any integration module that reads a
  credential-shaped environment variable directly.
- **FR-018** Vendor SDKs that sign internally MUST be adapted to route through the
  proxy, or replaced with a direct client. Which approach each vendor uses MUST be
  recorded in its integration docs.

**Audit and observability**

- **FR-019** Every resolution MUST be audited with tenant, team, integration,
  capability, timestamp, and outcome — never the value.
- **FR-020** The proxy MUST expose health, and report per-integration credential
  presence and validity without revealing values.
- **FR-021** A verification command MUST test a credential end-to-end against the
  vendor and report success or the specific failure.

### Key entities

| Entity | Description |
|---|---|
| **Credential** | Encrypted, versioned secret scoped to org/team and integration |
| **CredentialSchema** | Per-integration declaration of fields, types, and validation |
| **IntegrationHandle** | The non-secret reference a client sends instead of a secret |
| **InjectionRule** | How a given integration's secret enters the outbound request |
| **EgressAllowList** | Hosts an integration may reach |
| **ResolutionAudit** | The record of a resolution, without the value |

## Success criteria

- **SC-001** A red-team test inspecting the agent's environment, filesystem,
  prompt, tool arguments, and full trace finds no credential value. This is the
  feature's defining test.
- **SC-002** Every one of the ~85 integrations routes through the proxy — asserted
  by a catalogue-wide test, not by inspection.
- **SC-003** The CI direct-credential check fails on a deliberate violation
  fixture.
- **SC-004** Rotating a credential takes effect on the next request with no
  restart.
- **SC-005** A proxy outage produces a clear capability error with no fallback
  path — verified by a test that removes the proxy and asserts failure rather than
  degraded success.
- **SC-006** SigV4-signed AWS requests succeed with the signing key never present
  in the client process.
- **SC-007** Two teams with different credentials for the same vendor never
  cross-resolve.

## Out of scope

- Sandbox isolation of the execution environment (feature 009)
- Guardrail redaction of non-credential sensitive data (feature 008)
- Credential entry UI (feature 021)

## Clarifications

| Question | Resolution |
|---|---|
| Does the proxy add unacceptable latency? | It is a local hop in `dev` and an in-cluster hop otherwise. Measured overhead is budgeted at under 5ms p50; a capability's own network call dominates. |
| What about vendor SDKs that will not cooperate? | FR-018: either adapt the SDK's transport to the proxy, or write a direct client. The decision is recorded per integration; there is no third option that keeps the key in-process. |
| Is the proxy a single point of failure? | Yes, deliberately. FR-010 forbids a bypass, because a bypass is exactly the path an attacker or a rushed operator would use. Availability is addressed in feature 030 by running it alongside the agent. |
| How do long-lived connections handle rotation? | The proxy re-establishes the connection on rotation; capabilities holding streams must tolerate reconnection, which is documented in the base client contract. |
