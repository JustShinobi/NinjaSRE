# Tasks — 026 Protocol Bridges

## Phase 1 — Port and governance tests (test-first)

- **T001** `capabilities/protocols/port.py`: `ProtocolAdapter` — discover,
  describe, invoke, health.
- **T002** `capabilities/protocols/classification.py`: operator-assigned
  side-effect levels; unclassified defaults to write (FR-003).
- **T003** Add protocol constants to `config/constants/`: per-server tool cap,
  invocation timeout, result size limit.
- **T004** Write the unclassified-cannot-execute test (SC-002). Red.
- **T005** Write the control-parity test: compare a bridged invocation's controls
  and trace against a native one (SC-003). Red.
- **T006** Write the instruction-output test: instruction-shaped MCP output changes
  no agent behaviour (SC-005). Red.
- **T007** Write the malformed-schema and malformed-response rejection tests
  (SC-008). Red.
- **T008** Write the excess-tools reporting test (SC-007). Red.

## Phase 2 — MCP client

- **T009** `protocols/mcp/client.py`: stdio transport.
- **T010** `protocols/mcp/client.py`: HTTP transport (FR-001).
- **T011** `protocols/mcp/discovery.py`: tool listing → `BridgedCapability`
  (FR-002).
- **T012** `protocols/namespacing.py`: `<server>.<tool>` (FR-005).
- **T013** Test: a bridged tool cannot collide with a native capability name.
- **T014** `protocols/mcp/schema.py`: normalisation via feature 002; exclude
  unnormalisable tools with a recorded reason (FR-004).
- **T015** Per-call timeout (FR-008).
- **T016** Per-server tool cap with excess reported (FR-009); confirm SC-007.
- **T017** Malformed schema rejection with a specific error (FR-012); confirm the
  schema half of SC-008.

## Phase 3 — Invocation and governance

- **T018** `protocols/mcp/invocation.py`: invoke through the full control path
  (FR-011).
- **T019** `pre_tool_use` guardrails and approval gating for bridged tools.
- **T020** Sandbox execution for bridged invocations.
- **T021** `post_tool_use` guardrail filtering of MCP output; treated as data
  (FR-010); confirm SC-005.
- **T022** Trace recording identical in shape to native invocations.
- **T023** Confirm SC-003 control parity.
- **T024** Confirm SC-002: an unclassified tool cannot execute.
- **T025** Malformed response rejection (FR-012); confirm the response half of
  SC-008.

## Phase 4 — Registration lifecycle

- **T026** `protocols/registration.py`: team-scoped server registration through
  feature 013 (FR-001).
- **T027** Server credentials bound to the vault and used via the proxy (FR-006).
- **T028** Server health checks.
- **T029** Unavailable server excludes its tools with a recorded reason, without
  failing the investigation (FR-007); confirm SC-004.
- **T030** Tool-set refresh: new tools require classification, removed tools
  excluded cleanly (FR-013).
- **T031** Server-declared side effects shown to the operator as a suggestion,
  never as the effective classification.
- **T032** Console surface contract: servers, tools, classification status.
- **T033** Confirm SC-001: registered server tools appear and are invocable.

## Phase 5 — NinjaSRE MCP server

- **T034** `protocols/server/app.py`: MCP server implementation.
- **T035** `protocols/server/surface.py`: start investigation, read status and
  result, search memory, query topology, read catalogue (FR-014).
- **T036** `protocols/server/auth.py`: token requirement with permission and team
  scope enforcement (FR-015).
- **T037** Explicit refusal of configuration writes, credential access, and
  remediation execution (FR-016); confirm SC-006.
- **T038** Auditing of every external invocation (FR-017).
- **T039** Server enable/disable per deployment.

## Phase 6 — ACP and OpenClaw

- **T040** `protocols/acp/adapter.py` under the same governance (FR-018).
- **T041** [P] `protocols/openclaw/adapter.py` (FR-019).
- **T042** Both optional and inert when disabled (FR-020); test a deployment with
  neither enabled.
- **T043** Contract test: both adapters satisfy the `ProtocolAdapter` port and the
  governance parity assertions.

## Phase 7 — Verification and documentation

- **T044** End-to-end: register a real third-party MCP server, classify its tools,
  run an investigation using them.
- **T045** Egress allow-listing per registered server.
- **T046** Confirm all success criteria SC-001 through SC-008.
- **T047** Operator documentation: registering servers, classifying tools, the
  security model, exposing NinjaSRE's own server.
- **T048** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Registered MCP server tools appear and are invocable (SC-001)
- [ ] Unclassified bridged tools cannot execute (SC-002)
- [ ] Bridged invocations have full control parity with native ones (SC-003)
- [ ] Unavailable servers degrade without failing investigations (SC-004)
- [ ] Instruction-shaped output changes no behaviour (SC-005)
- [ ] Our MCP server enforces scope and refuses privileged operations (SC-006)
- [ ] Excess tools reported rather than dropped (SC-007)
- [ ] Malformed schemas and responses rejected specifically (SC-008)
- [ ] `make verify` green
