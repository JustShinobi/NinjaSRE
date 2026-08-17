# Bridging a protocol server

NinjaSRE ships the integrations its environment can validate. This is what to do when the one
you need is not among them and somebody has already built an MCP server for it.

A bridged server's tools appear in the capability catalogue beside the native
ones and are subject to every control the native ones are — guardrails, approval
gating, the sandbox, the credential proxy, and the trace. One thing is different
and it is deliberate: **NinjaSRE will not run a bridged tool until you say what
it does.**

## Register a server

Bridged servers live in the `capabilities` section of a team's configuration,
because a protocol server is a capability source.

```yaml
capabilities:
  protocol_servers:
    - name: deploys
      protocol: mcp          # mcp | acp | openclaw
      transport: http        # http | stdio
      url: https://mcp.internal.example/rpc
      credential: bridge_deploys   # the vault entry the proxy resolves
```

`name` is the namespace every one of that server's tools is prefixed with, so it
has to be lowercase with underscores and it must not contain `__`. A server
called `deploys` offering a tool called `rollout` becomes `deploys__rollout` in
the catalogue and `deploys.rollout` everywhere an operator reads it.

A stdio server declares a command instead of a URL:

```yaml
    - name: local_tooling
      transport: stdio
      command: ["mcp-local-tooling", "--stdio"]
```

Three rules the schema enforces at registration rather than at the first call:

- **An HTTP server must be `https`.** A bridged server reached over plain HTTP
  puts its credential on the wire in clear, and there is no toggle for that.
- **A stdio server cannot have a credential.** The only places to put one are
  the process's environment and its arguments, and NinjaSRE puts secrets in
  neither. If your local server needs to authenticate to something, expose it
  over HTTPS and give it a vault entry.
- **A team may register up to sixteen servers.** Every one of them is contacted
  before an investigation starts.

## Store its credential

The name in `credential` is the integration name the proxy resolves under. Store
the token against it the way you store any other:

```bash
ninjasre credentials set bridge_deploys --team payments
```

The secret is injected at the network edge as `Authorization: Bearer …`. Nothing
in the agent process — not the prompt, not a tool argument, not the trace —
holds it, and there is no configuration field that could.

The server's URL is also its egress allow-list. A request to any other host is
refused by the proxy *before* the vault is touched, so a bridged server cannot
be talked into fetching a secret for somewhere else.

## Classify its tools

A newly registered server's tools appear in the console as **awaiting
classification**. They are visible, they are scored, and they refuse to run.

For each one, decide what it does to the world and record it:

```yaml
capabilities:
  protocol_classifications:
    deploys.recent_rollouts: read
    deploys.rollout: write_reversible
```

The levels are the same five every native capability uses: `read`,
`read_sensitive`, `write_reversible`, `write_irreversible`, `destructive`.

### Why you have to do this

MCP lets a server declare its own tools read-only. NinjaSRE shows you that
declaration and does not act on it.

A third-party server's opinion about its own safety is not something to trust
with production. A server whose `delete_everything` tool is annotated
`readOnlyHint: true` — through carelessness, a bug, or malice — would otherwise
be a tool the agent may call without asking anybody. Article III's direction is
that absence is never permission, and a declaration you cannot verify is
absence.

So the server's hint becomes the pre-selected value in the console form, and
your decision is the one that has any effect.

**Anything above `read_sensitive` requires human approval per action**, exactly
as a native write does. A bridged tool has no rollback generator — nothing here
knows what the server did — so the approval prompt says so, in those words.

## What happens then

A classified tool is an ordinary capability. It is scored against the incident,
it competes for a slot in the turn, its arguments are scanned by the guardrail
engine before dispatch, its answer is scanned on the way back, and the call is
in the trace with its arguments and its evidence.

Bounds a bridged server runs inside, all of them named constants:

| Bound | Value | Why |
|---|---|---|
| Tools per server | 64 | A server with four hundred tools would crowd the catalogue |
| Servers per team | 16 | Each is contacted on the path to every investigation |
| Invocation timeout | 20s | A slow server must not hold a turn open |
| Discovery timeout | 5s | Paid before every investigation, not inside one |
| Answer size | 256 KiB | A megabyte in a trace is a query that should have been narrower |

## When something goes wrong

Everything below degrades the catalogue and none of it fails an investigation.

**The server is down.** Its tools are absent and the console says
`deploys: unavailable, its tools are excluded`. The investigation runs with what
is left.

**The server offers more than sixty-four tools.** The first sixty-four are
available and every excess tool is listed by name with `tool cap reached`. It is
reported rather than dropped, because "which tool is missing" is the question
you need answered.

**A tool's schema is malformed.** That tool alone is excluded, with an error
naming the tool and the field — `deploys.broken: malformed schema —
deploys.broken: inputSchema.properties is a list…`. Take it to whoever runs the
server. The rest of the catalogue is unaffected.

**A tool's schema cannot be normalised.** Rarer, and not the server's fault: a
schema whose root is an array, or one that requires an argument no provider
dialect would let the model supply. Excluded with `unnormalisable schema` and
the reason.

**The server's tool set changes.** On refresh, new tools arrive unclassified —
including a tool that was renamed, which is a new tool as far as this is
concerned. Removed tools take their classification with them, so a server that
later reuses the name does not inherit a decision you made about something else.

**The server returns instructions.** MCP output is data. It is recorded, it is
guardrail-filtered, and it reaches the model as a tool result like any other. A
tool's output cannot add a capability to a turn, cannot register a hook, and
cannot amend a prompt — none of those has a path from a tool result, by
construction.

## Exposing NinjaSRE's own MCP server

The other direction: another team's agent asks NinjaSRE what is wrong.

| Exposed | Not exposed |
|---|---|
| Start an investigation | Configuration writes |
| Read investigation status and result | Credential access of any kind |
| Search episodic memory | Remediation execution |
| Query service topology | Approval decisions |
| Read the capability catalogue | Identity and token management |

Read and investigate, and nothing else. The refused operations are refused *by
name* — an agent asking for `write_config` is told the surface is
read-and-investigate only, rather than being told the tool does not exist.

Every call needs an API token, and that token's permissions and team scope are
enforced against the same table the REST API uses: `investigation.run` to start
one, `investigation.read` to read it, `memory.read`, `knowledge.read`,
`config.read`. A token scoped to one team cannot address another. Every
invocation is audited, refusals included.

It is off unless a team asks for it, and it is asked for the way every other
surface is:

```yaml
surfaces:
  enabled: [cli, web_console, protocol_server]
```

Remove the entry and the listener answers every frame with
`NinjaSRE's protocol server is disabled in this deployment.` — configuration, so
switching it off during an incident is not a redeploy. A deployment that never
enables it has no listener at all.

## ACP and OpenClaw

Both are supported, both are optional, and both are governed identically: same
namespacing, same classification requirement, same caps, same trace. A
deployment that registers neither is unaffected — there is no adapter, no
listener, and nothing in the catalogue.

ACP peers expose agents rather than tools, and the classification requirement
matters more there rather than less: an agent on the other end decides for
itself what to do with an input, so what it does to the world is a question its
author cannot answer for every call and its operator must answer once.
