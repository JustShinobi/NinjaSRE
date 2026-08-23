# Specifications

31 features across 8 waves. Together they define the NinjaSRE MVP: the best of both
upstream projects, complete.

Every feature has `spec.md` (what and why), `plan.md` (how, with a Constitution
Check), and `tasks.md` (numbered, executable steps). Read
[`../docs/roadmap.md`](../docs/roadmap.md) for wave dependencies and exit criteria.

## Wave 0 — Foundation

Everything else compiles against these contracts.

| # | Feature | Delivers |
|---|---|---|
| [001](001-platform-foundation/spec.md) | Platform foundation | Four-tier layout, CI-enforced import boundaries, toolchain, config tier, provenance machinery |
| [002](002-llm-provider-layer/spec.md) | LLM provider layer | Nine providers at parity: tool calling, structured output, streaming, retry, schema normalisation, cost accounting |
| [003](003-capability-framework/spec.md) | Capability framework | Typed tools + methodology skills in one scored, bounded catalogue |
| [004](004-agent-runtime/spec.md) | Agent runtime | The canonical ReAct loop with all guardrails, sub-agents, parallel execution, hooks, handoff |
| [005](005-investigation-pipeline/spec.md) | Investigation pipeline | Six stages from raw alert to structured, evidence-backed diagnosis |
| [006](006-data-platform/spec.md) | Data platform | One Postgres with pgvector and Apache AGE behind twelve repository ports |

## Wave 1 — Trust & Safety

Constitutional invariants. No surface ships before these.

| # | Feature | Delivers |
|---|---|---|
| [007](007-credential-vault-and-proxy/spec.md) | Credential vault and proxy | The agent structurally cannot hold a secret |
| [008](008-guardrails-and-masking/spec.md) | Guardrails and masking | Reversible identifier masking before external LLM calls; YAML redact/block/audit rules |
| [009](009-sandbox-profiles/spec.md) | Sandbox profiles | Process, container, and Kubernetes isolation behind one contract |

## Wave 2 — Memory & Knowledge

The half that learns.

| # | Feature | Delivers |
|---|---|---|
| [010](010-episodic-memory/spec.md) | Episodic memory | Agent-driven recall of past investigations, with ablation switches |
| [011](011-strategy-synthesis/spec.md) | Strategy synthesis | Playbooks with anti-patterns mined from investigations that failed |
| [012](012-knowledge-graph-and-base/spec.md) | Knowledge graph and base | Service topology, blast radius, runbooks, reviewed agent proposals |

## Wave 3 — Control Plane

| # | Feature | Delivers |
|---|---|---|
| [013](013-hierarchical-config-service/spec.md) | Hierarchical config service | Org → team deep merge with locked, required, and approval-gated fields |
| [014](014-identity-rbac-sso-audit/spec.md) | Identity, RBAC, SSO, audit | Boundary-enforced permissions and an immutable audit log |
| [015](015-change-approval-and-policies/spec.md) | Change approval and policies | One approval mechanism for every gated change |
| [016](016-agent-runs-and-scheduler/spec.md) | Agent runs and scheduler | Replayable traces, live streaming with reconnection, exactly-once scheduling |

## Wave 4 — Action Governance

| # | Feature | Delivers |
|---|---|---|
| [017](017-remediation-and-rollback/spec.md) | Remediation and rollback | Read-only by default; approval and a rollback plan before every write |
| [018](018-human-in-the-loop/spec.md) | Human in the loop | Agent questions, mid-run context, takeover, cross-surface closure |

## Wave 5 — Surfaces

| # | Feature | Delivers |
|---|---|---|
| [019](019-cli-and-repl/spec.md) | CLI and REPL | One-command install, scriptable CLI, stateful interactive shell |
| [020](020-rest-api-and-alert-ingestion/spec.md) | REST API and alert ingestion | The contract every surface consumes, plus verified webhook ingestion |
| [021](021-web-console/spec.md) | Web console | Live and replayed investigations, memory hub, config editor, approvals |
| [022](022-chat-bots/spec.md) | Chat surfaces | Slack, Teams, Telegram, Discord behind one contract |
| [023](023-notifications-and-reporting/spec.md) | Notifications and reporting | Thirteen destinations, Pushover, cooldown, escalation with cancellation |

## Wave 6 — Integrations

| # | Feature | Delivers |
|---|---|---|
| [024](024-integration-framework/spec.md) | Integration framework | The seven-artefact anatomy that makes 86 integrations tractable |
| [025](025-integration-catalog-parity/spec.md) | Integration catalogue parity | All 86 integrations at full parity, delivered in three tiers |
| [026](026-protocol-bridges/spec.md) | Protocol bridges | MCP, ACP, OpenClaw — under the same governance as native capabilities |

## Wave 7 — Evaluation

The half that measures. This is what makes "it learns" checkable.

| # | Feature | Delivers |
|---|---|---|
| [027](027-synthetic-scenario-harness/spec.md) | Synthetic scenario harness | Ground-truth scenarios and mock backends, runnable offline with no credentials |
| [028](028-evaluation-and-ablation/spec.md) | Evaluation and ablation | Five-axis scoring, golden trajectories, CI regression gates, and the ablation harness |
| [029](029-chaos-and-e2e-suites/spec.md) | Chaos and e2e suites | Real faults in real infrastructure, feeding misses back into the fast suite |

## Wave 8 — Operations

| # | Feature | Delivers |
|---|---|---|
| [030](030-deployment-profiles/spec.md) | Deployment profiles | Dev, standard, and enterprise, with backup, upgrade, keys, and air-gapped operation |
| [031](031-observability-and-docs/spec.md) | Observability and docs | Opt-in OpenTelemetry, generated reference documentation, an executable quickstart |

---

## Working on a feature

1. Read the feature's `spec.md` — requirements, success criteria, and clarifications.
2. Read `plan.md` — technical approach, Constitution Check, provenance, and risks.
3. Work through `tasks.md` in order. `[P]` marks tasks with no dependency on
   another unfinished task in the same phase.
4. Every feature is test-first: the tests that define its success criteria are
   written before the implementation that satisfies them.
5. A feature is done when every box in its Definition of Done is ticked.

## Before writing any code

Read [`../.specify/memory/constitution.md`](../.specify/memory/constitution.md).
Every `plan.md` passes a Constitution Check against it, and a plan that violates an
article without a recorded justification is rejected.
