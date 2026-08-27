# Deviations — 026 Protocol Bridges

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. Namespacing is `<server>__<tool>`, not `<server>.<tool>` (T012, FR-005)

The plan's technical-context table says the namespace separator is a dot. A dot
cannot be the *callable* name, for two independent reasons that both come from
this repository rather than from a preference:

- `core/capability/metadata.TOOL_NAME_PATTERN` is `^[a-z][a-z0-9_]*$`. A
  `ToolMetadata` whose name contains a dot cannot be constructed at all.
- Every provider dialect's `name_allowed_pattern` in `core/llm/schema.py` is
  `[^a-zA-Z0-9_-]`, so `normalise_tool_name` would rewrite `deploys.rollout` to
  `deploys_rollout` on the way to the model. That is precisely the failure the
  comment above `TOOL_NAME_PATTERN` warns about: "a renamed tool is a tool the
  trace cannot match back to its declaration."

So the dot form is kept where it is a human-facing identifier and the underscore
form is the callable name. `namespacing.py` produces both:

| Form | Spelling | Used for |
|---|---|---|
| Qualified | `deploys.rollout` | The console, the classification key, exclusion records, audit detail |
| Catalogue | `deploys__rollout` | `ToolMetadata.name` — what the model calls |

The classification table is keyed by the *qualified* name deliberately, so an
operator's decision survives a change to the cleaning rules for the callable
one.

**FR-005's actual requirement — collisions are impossible — is stronger than the
plan's spelling and is met.** Two bridged tools cannot collide because a server
name may not contain `__` (refused at registration), so `(server, tool)` maps
injectively onto the joined name. A bridged tool cannot collide with a native
one because no native capability name contains `__` at all, and
`test_no_native_capability_name_could_be_mistaken_for_a_bridged_one` asserts
that against the built registry rather than assuming it.

## 2. Three modules the plan's tree does not name

The plan's `## Project structure` is a sketch; three files exist that it does
not list, and each one exists because putting its contents where the plan
implies would have made the governance per-protocol instead of shared.

- **`protocols/catalogue.py`.** The plan implies `mcp/discovery.py` turns a tool
  listing into a `BridgedCapability`. The *MCP* half of that is in
  `mcp/discovery.py`; the part that is not MCP — the per-server cap with its
  excess named, the classification lookup, the refusing body for an
  unclassified tool, and the construction of the `RegisteredTool` — is here, so
  ACP and OpenClaw get it identically. `tests/contract/protocols/test_every_adapter.py`
  is parameterised over all three precisely to hold that.
- **`protocols/schema.py`** rather than the plan's `mcp/schema.py`. ACP and
  OpenClaw declare JSON Schema too, and `acp/adapter.py` importing
  `mcp/schema.py` would have been a dependency that says the wrong thing about
  which protocol owns the rule.
- **`protocols/peer.py`.** One HTTP-JSON transport through the credential proxy,
  shared by ACP and OpenClaw. MCP keeps its own in `mcp/client.py` because
  JSON-RPC framing is not a document `GET`.

Plus `mcp/adapter.py`, which composes the three MCP modules into the
`ProtocolAdapter` the port describes. The plan lists the three parts and not the
thing that assembles them.

## 3. Registration lives in the `capabilities` config section, not a seventh one (T026)

FR-001 asks for servers registrable per team through configuration, which means
feature 013's schema. That schema is closed at six sections and says so in
`schema/root.py`: "Six sections and nothing else. That closure is what makes the
rest of the feature possible."

Two typed fields were added to `CapabilitiesConfig` instead of a seventh
section: `protocol_servers` (a `tuple[ProtocolServerSettings, ...]`) and
`protocol_classifications` (a `Mapping[str, str]`). A protocol server is a
capability *source* — the same kind of thing as the shipped catalogue, arriving
from somewhere else — so the capabilities section is where it belongs, and this
is the sanctioned way to add configuration ("Adding a field is a schema change …
a typed field on the owning section, with a default").

`protocol_classifications` is deliberately **not** added to
`RootConfig.capability_references()`. Those names are cross-referenced against
the live native catalogue at write time, and every bridged tool would be
reported as a dangling reference. Asserted by
`test_a_bridged_tool_name_is_not_cross_referenced_against_the_native_catalogue`.

## 4. The server's enable switch is configuration, not an environment variable (T039)

Written first as `NINJASRE_PROTOCOL_SERVER_ENABLED` with the constant in
`config/constants/protocols.py`. `make check-credentials` refused it, and the
rule it broke is right: *any* read of the process environment from
`capabilities/` is a violation, "not only credential-shaped ones — a vendor
client and an agent-callable tool have no business reading the environment at
all."

Replaced with `SURFACE_PROTOCOL_SERVER = "protocol_server"`, a sixth entry in
`SURFACE_IDENTIFIERS`, enabled the way every other surface is:

```yaml
surfaces:
  enabled: [cli, web_console, protocol_server]
```

`enabled_for(surfaces)` reads it, and absence is off. This is better than what
was planned rather than a concession: it is per team rather than per process, it
is visible in the console, and switching it off during an incident is a
configuration edit rather than a restart.

## 5. A stdio server cannot be authenticated, and says so at registration

FR-006 says server authentication uses vault credentials via the proxy. That is
implementable for HTTP and *not* implementable for stdio: the only ways to give
a local command a secret are its environment and its argument vector, and
Article IV forbids both. There is no third option — the proxy attaches a secret
to an HTTP request, and a subprocess is not one.

Rather than leaving the gap silent, `ServerRegistration.__post_init__` refuses a
stdio registration that declares any authentication, with an error naming the
reason and the remedy ("expose the server over https instead"). Asserted by
`test_a_stdio_server_may_not_be_given_a_credential`. The stdio transport also
sends an explicitly empty `environment` to the sandbox, with a comment saying
why it stays empty.

## 6. stdio runs one sandboxed process per exchange (T009, T020)

`platform.sandbox.Sandbox.execute` runs a command to completion. An MCP stdio
server reads newline-delimited JSON-RPC from stdin and exits at EOF, so one
exchange is: initialise, `notifications/initialized`, the call, EOF — sent as
one `stdin` payload, answered on stdout, parsed by matching the request id.

The alternative — a long-lived subprocess held across calls — would need a
seventh method on the `Sandbox` port (the port's docstring closes the list at
six and explains why), or a bare `create_subprocess_exec` that puts a
third-party binary on the host beside the agent's own file descriptors. The
cost of the chosen shape is one process start per call inside a sandbox that was
going to be provisioned anyway; the benefit is that a bridged server has no
lifetime the reaper does not already understand.

This is also how T020 ("sandbox execution for bridged invocations") is
satisfied. For an HTTP bridged server there is no local execution to sandbox at
all — the isolation on that path is the proxy's per-server egress allow-list,
which is T045 and is asserted separately.

## 7. T044's "real third-party MCP server" is a real server, in process

There is no third-party MCP server this suite may reach: `make verify` runs
offline on three platforms, a networked test is a skipped test, and a skipped
test is not a success criterion.

`tests/contract/protocols/test_bridged_end_to_end.py` therefore stands up an
MCP server that is real in every respect except its location — it parses the
JSON-RPC frames off the wire and answers them — as the `OutboundSender` behind a
genuine `ProxyEngine`, with a genuine `Vault` entry, a genuine
`InjectionRuleRegistry` built from the registration's own rule, and the real
`ReActLoop` on the near side. Nothing on the path under test is stubbed: the
frames, the injection, the egress allow-list, the catalogue build, the
classification gate, and the loop are all the shipping code.

What that suite proves and a networked one would not: the credential reached the
server as `Authorization: Bearer …` on every call, and appears in neither the
answer, the input schema the model is shown, the tool description, nor the trace
record.

## 8. ACP and OpenClaw wire shapes are unverified against a live peer

Both adapters are implemented, both satisfy the port, and both are covered by
the same parameterised governance suite as MCP. What has *not* happened is a
call to a real ACP peer or a real OpenClaw source, for the same reason as §7.

The document shapes implemented are: ACP `GET /agents` → a list of
`{name, description, input}` and `POST /runs` with `{agent_name, input}` →
`{status, output}`; OpenClaw `GET /capabilities` → a list of
`{name, description, parameters, side_effect}` and
`POST /capabilities/{name}/invoke` with `{arguments}` → `{result}`. If either
protocol's shape differs in a deployment, the change is confined to the ~40 lines
of that adapter that read a document — which is the property the port exists to
give, and which the shared governance suite will keep honest.

## 9. T048 not done: `docs/provenance-map.md` is gitignored and `make check-provenance` does not exist

Same as feature 020's §6 and for the same reason. `docs/provenance-map.md` is in
`.gitignore` and `CLAUDE.md` forbids a committed file depending on it, so editing
the local copy changes nothing that ships. There is no `check-provenance` target
in the `Makefile` — the gate is the fifteen checks `verify` runs, and all fifteen
pass.

T047's operator documentation was written: `docs/protocol-bridges.md`, and
`capabilities/AGENTS.md` gained the two rules specific to a capability the
repository did not declare.

## 10. Test-first sequencing, adapted for scale (same as 020 §7)

Phase 1 as written asks for T004–T008 — five sophisticated governance tests —
written and red before any of Phases 2–6 exist. Against a package that does not
exist those five fail on `ImportError`, which proves nothing about the behaviour
they describe.

What was actually done, module by module: the test file landed first, was run,
and was confirmed failing, then the module was written. `test_namespacing.py`,
`test_classification.py`, `test_bridged_catalogue.py`, `test_bridged_schema.py`,
`test_mcp_client.py`, `test_registration.py` and
`test_protocol_server_settings.py` each went red before their module existed.
The success-criterion suites (SC-002, SC-003, SC-005 in
`test_governance_parity.py`; SC-001 and SC-004 in `test_bridged_end_to_end.py`;
the per-protocol suite in `test_every_adapter.py`) were written once there was
enough behind them to make the assertion about behaviour rather than about
imports — and every one of them exercises real collaborators: the real
`dispatch_calls`, the real `GuardrailHooks` over a real `Ruleset`, the real
`GatingPolicy`, the real `ProxyEngine`, the real `ReActLoop`, the real
permission table.

## 11. Two test modules renamed for pytest's basename rule

`tests/unit/capabilities/protocols/test_catalogue.py` and `test_schema.py`
collided with the existing `tests/unit/platform/config_service/test_catalogue.py`
and `test_schema.py`. pytest imports test modules by basename when there is no
package `__init__.py`, so the collision is a collection error rather than a
style issue. Renamed to `test_bridged_catalogue.py` and `test_bridged_schema.py`.

## 12. One line shaped by `make check-raw-sql`

`StdioMcpTransport.request` binds `sandbox = self._sandbox` before calling
`sandbox.execute(...)`. `check_raw_sql.py` exempts the *receiver* rather than the
method — `NON_STORAGE_EXECUTE_RECEIVERS = {"sandbox", "executor"}` — and
`self._sandbox.execute` presents `_sandbox` as the receiver. The check is right
about the boundary it holds and was not touched; the local binding is the
one-line change that says what the code already meant.

## 13. The task brief's baseline test count was stale

The brief states "4223 passed, 15 skipped". The actual baseline on this branch,
measured by stashing this feature's changes and collecting, is **8300** tests.
After this feature: 8494 collected, `make verify` reports **8479 passed, 15
skipped** — 194 new tests, no pre-existing failures, and none introduced.
