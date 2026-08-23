# Feature 026 — Protocol Bridges

- **Wave:** 6 — Integrations
- **Branch:** `feat/026-protocol-bridges`
- **Status:** Draft
- **Depends on:** 003, 007, 013, 024

## Summary

Extension beyond the built-in catalogue: MCP (client and server), ACP, and
OpenClaw. An operator connects a third-party MCP server and its tools appear in
the catalogue under the same governance as native capabilities — side-effect
classification, credential proxying, approval gating, and trace recording. And
NinjaSRE exposes itself as an MCP server so other agents can invoke investigations.

## User scenarios

### Primary story

A team runs an internal MCP server exposing their bespoke deployment system. They
register it in the console. Its tools appear in the capability catalogue, each
requiring an explicit side-effect classification before use. The agent invokes
them during an investigation, and every call is proxied, gated, and traced exactly
like a native capability.

### Acceptance scenarios

1. **Given** an MCP server is registered, **when** the catalogue builds, **then**
   its tools appear with metadata derived from the server's declarations.
2. **Given** an MCP tool with no declared side effect, **when** it is registered,
   **then** it is treated as write and requires an operator classification before
   it may execute.
3. **Given** an MCP tool invocation, **when** it runs, **then** it is subject to
   guardrails, approval gating, sandbox execution, and trace recording exactly like
   a native capability.
4. **Given** an MCP server requiring authentication, **when** it is called, **then**
   credentials come from the vault via the proxy, never from the agent context.
5. **Given** an MCP server that becomes unavailable, **when** the catalogue
   resolves, **then** its tools are excluded with a recorded reason and the
   investigation continues.
6. **Given** NinjaSRE's MCP server, **when** an external client connects, **then**
   it can start an investigation and read results, subject to token permissions.
7. **Given** an MCP server returning a malformed tool schema, **when** it is
   registered, **then** it is rejected with a specific error rather than breaking
   the catalogue.
8. **Given** an MCP server whose tool set changes, **when** it is refreshed,
   **then** new tools require classification and removed tools are excluded
   cleanly.

### Edge cases

- An MCP server with hundreds of tools flooding the catalogue.
- A tool name colliding with a native capability.
- A server that is slow enough to stall a turn.
- A tool whose schema uses constructs a given LLM provider rejects.
- An MCP server attempting to return instructions rather than data.
- A server requiring interactive authentication.

## Requirements

### Functional

**MCP client**

- **FR-001** MCP servers MUST be registrable per team through configuration, with
  stdio and HTTP transports supported.
- **FR-002** Discovered tools MUST enter the same catalogue as native capabilities,
  with metadata derived from the server's declarations.
- **FR-003** A tool with no declared side effect MUST be treated as write and MUST
  require an explicit operator classification before it may execute.
- **FR-004** MCP tool schemas MUST pass provider normalisation (feature 002); one
  that cannot be normalised MUST be excluded with a recorded reason.
- **FR-005** Tool names MUST be namespaced by server, so collisions with native
  capabilities are impossible.
- **FR-006** Server authentication MUST use vault credentials via the proxy.
- **FR-007** An unavailable server MUST exclude its tools with a recorded reason,
  never fail the investigation.
- **FR-008** Server calls MUST have a timeout so a slow server cannot stall a turn.
- **FR-009** The number of tools a server may contribute MUST be capped by a named
  constant, with excess reported.
- **FR-010** MCP tool **output** MUST be treated as data, never as instructions,
  and MUST pass the guardrail engine.
- **FR-011** MCP tool invocations MUST be subject to guardrails, approval gating,
  sandbox execution, and trace recording identically to native capabilities.
- **FR-012** A malformed server response MUST be rejected with a specific error.
- **FR-013** Tool-set refresh MUST require classification for new tools and cleanly
  exclude removed ones.

**MCP server**

- **FR-014** NinjaSRE MUST expose an MCP server allowing external clients to: start
  an investigation, read its status and result, search memory, and query topology.
- **FR-015** Server access MUST require a token, and MUST enforce that token's
  permissions and team scope.
- **FR-016** The server MUST NOT expose configuration writes, credential access, or
  remediation execution.
- **FR-017** Every external invocation MUST be audited.

**ACP and OpenClaw**

- **FR-018** ACP MUST be supported for agent-to-agent interoperation, subject to
  the same governance as MCP.
- **FR-019** OpenClaw MUST be supported as a capability source with the same
  classification requirement.
- **FR-020** Both MUST be optional and MUST NOT affect a deployment that does not
  enable them.

### Key entities

| Entity | Description |
|---|---|
| **McpServerRegistration** | A configured server: transport, credentials, team scope |
| **BridgedCapability** | An external tool surfaced in the catalogue |
| **Classification** | The operator-assigned side-effect level for a bridged tool |
| **ProtocolAdapter** | MCP, ACP, or OpenClaw implementation of the bridge port |
| **ExposedSurface** | What NinjaSRE's own MCP server offers |

## Success criteria

- **SC-001** A registered MCP server's tools appear in the catalogue and are
  invocable by the agent.
- **SC-002** An unclassified bridged tool cannot execute — asserted by attempting
  it.
- **SC-003** Bridged invocations pass through guardrails, approval gating, sandbox,
  and trace recording — verified by comparing a bridged and a native invocation's
  trace and controls.
- **SC-004** An unavailable server degrades the catalogue without failing the
  investigation.
- **SC-005** A server returning instruction-shaped output does not influence agent
  behaviour beyond being recorded as data.
- **SC-006** NinjaSRE's MCP server enforces token permissions and refuses
  configuration, credential, and remediation operations.
- **SC-007** A server contributing more than the tool cap has its excess reported
  rather than silently dropped.
- **SC-008** A malformed schema or response is rejected with a specific error and
  does not break the catalogue.

## Out of scope

- Native integrations (feature 025)
- MCP servers maintained by NinjaSRE for third-party systems — the point is to
  consume the community's

## Clarifications

| Question | Resolution |
|---|---|
| Why require operator classification for bridged tools? | A third-party server's declaration of its own side effects is not something to trust with production. Article III's fail-safe direction — unclassified means write — plus explicit operator classification is the only defensible default. |
| Does MCP make native integrations unnecessary? | No. Native integrations carry methodology, verifiers, bounded reads, rollback generators, and scenarios. MCP is an extension path for what the catalogue does not cover, not a replacement for parity. |
| Is MCP output a prompt-injection risk? | Yes, and it is handled the same way as any observed content: data, never instructions (FR-010), guardrail-filtered, with SC-005 asserting instruction-shaped output does not change behaviour. |
| Why expose an MCP server at all? | So NinjaSRE composes into other teams' agent workflows — a coding agent can ask it to investigate a failing deploy. Read-and-investigate only (FR-016); nothing that changes configuration or production. |
