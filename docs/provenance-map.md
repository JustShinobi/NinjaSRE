# Provenance Map

Authoritative record of what NinjaSRE takes from each upstream, how, and why.
Required by Constitution Article XIII. Update this file in the same change that
introduces or modifies derived code.

## Upstreams

| Key | Project | Licence | Reference |
|---|---|---|---|
| **T** | [Tracer-Cloud/opensre](https://github.com/Tracer-Cloud/opensre) | Apache 2.0 | ~222k LOC production Python, 76 integrations, layered architecture, evaluation environment |
| **S** | [swapnildahiphale/OpenSRE](https://github.com/swapnildahiphale/OpenSRE) | Apache 2.0 | ~96k LOC Python + ~33k TS, 51 skills, episodic memory, multi-tenant console |

Both are Apache 2.0, so derivation is permitted with attribution. `NOTICE` must
name both. Every derived file carries a header:

```python
# Derived from <PROJECT> <path> (Apache-2.0).
# Modification: <adopted | adapted | rewritten> — <one line on what changed>.
```

## Disposition legend

| Disposition | Meaning |
|---|---|
| **ADOPT** | Ported with minimal change — renames, import paths, type tightening only |
| **ADAPT** | Structure and algorithm kept; reworked for NinjaSRE's ports, storage, or constitution |
| **REWRITE** | Idea kept, implementation new — the upstream code does not fit the target architecture |
| **REFERENCE** | Not ported; used as design input or test corpus |
| **REJECT** | Deliberately not carried over |

---

## 1. Agent runtime and investigation

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `tools/investigation/lifecycle.py` | ADAPT | `core/pipeline/lifecycle.py` | Six-stage ordering kept; stage signature normalised to `(state) -> updates`, merge concentrated in `apply_state_updates`, failure annotated with stage identity and re-raised, run-end hook fires once in a `finally`. **Landed in 005.** |
| T | `tools/investigation/stages/{intake,plan_evidence,gather_evidence,diagnose,resolve_integrations}/` | ADAPT | `core/pipeline/stages/` | Stage logic ported; capability selection extended to cover skills. Gathering thinned to a runtime invocation (the loop moved to 004). Deduplication and the zero-integration outcome are new. **Landed in 005.** |
| T | `tools/investigation/streaming.py` + S `sre-agent/events.py` | ADAPT | `core/pipeline/streaming.py` | Thirteen typed events; the event *names* follow S's SSE vocabulary so a surface written against it needs no translation. Replay to an `InvestigationView` is new and is what SC-005 asserts. **Landed in 005.** |
| T | `core/llm/parsers/root_cause.py` | ADAPT | `core/pipeline/stages/diagnose/fallback.py` | Degraded prose parser. Category matching rewritten against the versioned taxonomy's own descriptions; every result carries `fallback_used` so a corpus can separate the two paths. **Landed in 005.** |
| T | `tools/investigation/stages/gather_evidence/{agent,loop,tools,prompt}.py` | ADAPT | `core/agent/react_loop.py`, `core/agent/execution.py` | The bounded ReAct loop. Guardrails preserved; sub-agent dispatch and bounded parallel execution added. **Landed in 004.** |
| T | `core/agent/{agent,react_loop,goals,loop_host,mixins,provider_hooks,run_io}.py` | ADAPT | `core/agent/` | Runtime skeleton |
| T | `core/context_budget.py` | ADAPT | `core/agent/context_budget.py` | Value function rewritten around four named terms (recency, citation, size, source reliability) with a golden test pinning the ordering. **Landed in 004.** |
| T | `core/state/` | ADAPT | `core/state/` | `AgentState`, six frozen slices, `EvidenceEntry`. Extended with memory and approval slices; the pipeline's `EvidenceEntry` adds arguments, an absolute timestamp, and provenance over the runtime's. Slice ownership is a table read by a test rather than a convention. **Landed in 005.** |
| T | `core/domain/` (alerts, correlation, diagnosis, types) | ADOPT | `core/domain/` | Pure rules with no external dependency; highest-value direct reuse. Eight alert adapters, the incident window, the fingerprint, the versioned taxonomy, the diagnosis result. **Landed in 005.** |
| — | `core/pipeline/{ports,ownership,state_factory,accounting,runtime_bridge,build}.py`, `stages/window_guard.py` | NEW | — | Written for 005. The tier table puts the catalogue resolver, the ranker, the incident index, and the delivery destinations above `core/`, so each is a port here with a neutral default and a tier-2 adapter in `capabilities/registry/planning.py`. The window guard is a `pre_tool_use` hook reading its window from the session it is guarding. |
| T | `core/agent_harness/turns/` | ADAPT | `core/agent/turn.py`, `core/agent/compaction.py` | Turn record and transcript compaction. Accounting rides on `core.llm.usage`. **Landed in 004.** |
| T | `core/agent_harness/prompts/` | ADAPT | `config/prompts/` | Prompt constants move to the config tier per Article VIII |
| S | `sre-agent/agent.py` (75KB) | REWRITE | `core/agent/subagents/`, `core/agent/hooks/` | Sub-agent registry and lifecycle hooks are the valuable ideas; the monolith and the SDK coupling are not. Both became packages rather than modules. **Landed in 004.** |
| S | `sre-agent/message_queue.py` | ADAPT | `core/agent/message_queue.py` | Mid-run message merge with debounce at turn boundaries. Debounce measured from the last message rather than the first. **Landed in 004.** |
| S | Claude Agent SDK session model | REFERENCE | `core/agent/runtime_port.py`, `core/agent/adapters/claude_sdk.py` | Contract shape informs the port; the SDK is experimental-only per Article V and its unenforceable guardrails are listed in the adapter. **Landed in 004.** |
| S | `AskUserQuestion` pattern | ADAPT | `core/agent/handoff.py` | Human-handoff capability with a channel port, a configured timeout, and default-deny on expiry. **Landed in 004.** |
| S | SDK background-task lifecycle | REFERENCE | `core/agent/subagents/dispatch.py` | Informs the fan-out and isolation model; no code carried over. **Landed in 004.** |
| — | `core/agent/{session,stagnation,tool_cache,seed_calls,conclusion,degradation,guard,store}.py` | NEW | — | Written for 004. The tool cache and the degradation path are the same *ideas* as T's `InvestigationToolCallCache` and `degraded_investigation_from_llm_failure`, rewritten against this repository's result and session types rather than ported. |
| S | `sre-agent/server.py`, `server_simple.py` (33KB + 51KB) | REJECT | — | Two divergent server implementations; NinjaSRE has one API layer with sandbox as a profile, not a fork |

## 2. LLM provider layer

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `core/llm/providers/` | ADOPT | `core/llm/providers/` | Anthropic, OpenAI, Azure OpenAI, Vertex, Bedrock, OpenRouter, NIM, Ollama, Gemini |
| T | `core/llm/transports/{sdk,litellm}/` | ADAPT | `core/llm/transports/` | Dual transport retained; LiteLLM stays optional |
| T | `core/llm/shared/tool_schema_normalize.py` | ADOPT | `core/llm/schema.py` | Critical: draft-07 constructs that pass local validation but fail provider APIs |
| T | `core/llm/shared/{llm_retry,structured_output,usage}.py` | ADOPT | `core/llm/shared/` | Retry, structured output, token accounting |
| T | `core/llm/transports/sdk/anthropic_cache.py` | ADAPT | `core/llm/cache.py` | Prompt caching; the shared-client race documented upstream is fixed by construction |
| T | `core/llm/failure_classification.py`, `core/llm_invoke_errors.py` | ADOPT | `core/llm/failures.py` | Degradation instead of crash |
| T | `core/agent_harness/accounting/` | ADAPT | `platform/observability/accounting.py` | Per-session/per-run token and cost accounting |
| S | LiteLLM proxy config | REFERENCE | `deploy/compose/litellm/` | Optional multi-provider proxy remains available; not the primary path |

## 3. Capability model

**Status: delivered in feature 003.** Destinations below are the ones that
actually shipped, which differ from the plan in three places — noted inline.

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `core/tool_framework/` | ADAPT | `core/capability/` | **Flat, not `core/capability/tool/`.** `decorator.py`, `base.py`, `registered.py`, `metadata.py`, `schema.py`, `telemetry.py`, `result.py`, `ports.py`, `tokens.py`, `types.py`. A `tool/` subpackage would have implied a `skill/` sibling, but skills are data plus a loader, not a second framework |
| T | `tools/registry_discovery.py`, `registry.py`, `registry_index.py` | ADAPT | `capabilities/registry/discovery.py`, `catalogue.py` | Package-walk discovery extended to skills. Discovery returns duplicates rather than resolving them, so validation can name both sources |
| T | `core/tool_framework/skill_guidance.py`, `tools/registry_skill_guidance.py` | ADAPT | `capabilities/registry/validation.py`, `selection.py` | **No `guidance.py`.** The skill-to-tool binding became declarative: `directs_tools` in the manifest, resolved at build time by validation and expanded at selection time. A runtime bridging module would have made a dangling reference a runtime failure, which is the thing the feature exists to prevent |
| T | `tools/investigation/stages/plan_evidence/`, `core/domain/alerts/tool_planning.py` | ADOPT | `capabilities/registry/scoring.py` | **Landed here, not in a pipeline stage.** Scoring belongs to the catalogue, so the planning stage (005) supplies `planned_capabilities` and the scorer stays usable without a pipeline |
| T | `tools/investigation/stages/gather_evidence/tools.py` cap logic | ADOPT | `capabilities/registry/selection.py` | Cap, secondary reserve, skill expansion, rationale recording |
| T | `core/tool_framework/telemetry.py` | ADOPT | `core/capability/telemetry.py` | Extended: arguments filtered on the way in, and a JSON round trip proven sufficient to replay the call |
| S | `sre-agent/.claude/skills/{investigate,observability,infrastructure,remediation}/SKILL.md` | ADAPT | `capabilities/skills/<id>/SKILL.md` | **High-value, and the four cross-vendor skills upstream has.** See the adaptation record below |
| S | `sre-agent/.claude/skills/<domain>-<vendor>/SKILL.md` (40 files) | DEFER | features 024–025 | Cannot land before the integrations: a vendor skill's `directs_tools` names vendor tools, and `dangling-directed-tool` rejects the build until those exist. The seven `_templates/` written in 003 carry the per-domain methodology for ~36 of them |
| S | `sre-agent/.claude/skills/{memory-search,knowledge-base,knowledge-raptor,incident-*,alerting-context}/SKILL.md` (7 files) | DEFER | features 010, 012, 018, 020, 023 | Cross-vendor, but each belongs to the feature that owns its store or surface |
| S | `sre-agent/.claude/skills/*/scripts/*.py` | ADAPT | `capabilities/tools/<domain>/`, `integrations/<vendor>/client.py` | ~250 scripts. Client logic becomes integration clients; per-action scripts become typed tools. Deferred to 024–025; 003 ships only the vendor-free `system/` and `remediation/` tools |
| S | Progressive disclosure (metadata-then-body loading) | ADOPT | `capabilities/registry/disclosure.py` | Directly relieves the schema cap pressure in T's design. `DiscoveredSkill` holds a path rather than the body, so nothing incidental can load it |
| S | Frontmatter manifest format | ADAPT | `capabilities/registry/frontmatter.py` | **Not a YAML dependency.** A ~180-line reader accepting scalars, flat lists in either notation, and one level of nesting, rejecting everything else by name. YAML's implicit typing would silently turn `no` into `False` in a hand-written manifest |
| S | Credential-proxy-aware client pattern (`get_config()` reading tenant/team, never secrets) | ADOPT | `integrations/_base/client.py` | Becomes the mandatory base for every integration client |

### Adaptation record — the four cross-vendor skills

Written in NinjaSRE's own voice against the upstream files, not copied. What
crossed over, and what did not, because the second list is the part a reviewer
should be able to challenge.

**Carried across:**

| From | To | Note |
|---|---|---|
| Five-phase framework | `investigate` | Kept, with an exit condition added per phase |
| Ranked hypotheses (H1/H2/H3) with supporting *and* refuting evidence | `investigate` | The refuting half is the load-bearing part |
| "After you have concrete evidence, not on the raw alert alone" — the recall ordering rule | `investigate`, phase 3 | Subtle and easy to lose; promoted to its own phase |
| 6–8 tool calls per phase | `investigate` | Stated as a budget, with what exceeding it means |
| Structured conclusion (root cause / evidence / confidence / actions / caveats) | `investigate` | Reformatted; `timeline` added |
| Intellectual-honesty section — observed vs inferred, say "I don't know" | `investigate` | Almost verbatim in intent |
| "Don't repeat queries with the same parameters" | `investigate` | The duplicate-call cache makes this enforceable later |
| Statistics before samples: volume → distribution → trend → sample | `observability` | Upstream's four steps, which are better than the three I first wrote |
| Error clustering, temporal patterns, service correlation | `observability` | As the three named patterns worth looking for |
| "Credentials are injected by a proxy — do NOT check env vars" | `observability` | Restated for the credential proxy. This *is* Article IV, and upstream states it better than the constitution does |
| Structured log-analysis output | `observability` | Reformatted, with "quote, don't paraphrase" added |
| **"Get pod events (ALWAYS check first!)"** | `infrastructure` | Promoted to the skill's opening section and its title. The densest single rule in the upstream set |
| Symptom → first action table (CrashLoopBackOff, OOMKilled, Pending, rollout stuck) | `infrastructure` | Kept as a table, with the *why* column added and the script column dropped |
| Dry-run-first safety principle | `remediation` | Becomes the generated rollback plan, read before approval |
| Diagnose → propose → confirm → execute → verify | `remediation` | Kept as the six-step sequence, with "read the plan" inserted |
| Proposed-remediation format (action / target / reason / risk) | `remediation` | Kept, with `rollback` and `verify` lines added |
| Scenario → action mapping | `remediation` | Rewritten as a table naming the typed tools |

**Deliberately not carried across:**

| What | Why |
|---|---|
| `python .claude/skills/**/scripts/*.py` invocations throughout | ADR 0002. A skill directs typed tools; shell routes around approval, rollback, and audit. `body_violations` rejects it at build time, so this is enforced rather than trusted |
| `--dry-run` flags on scripts | Replaced by the rollback plan, which is generated before approval and is specific to the arguments |
| Subagent dispatch table (`log-analyst`, `k8s-debugger`, `remediator`) | Article V — those are Agent SDK constructs, not the canonical runtime. Sub-agents are feature 004's decision to make |
| `/skill-name` invocation syntax | Another runtime's Skill tool. Here a skill is selected by the scorer, never called |
| Backend inventory (Coralogix, Datadog, Splunk, …) listed in the skill body | Premature: those integrations arrive in 024–025, and the resolved catalogue already tells a team which backends it has |
| `infrastructure` limited to Kubernetes and AWS | Widened to the layer ordering, which holds for any control plane |
| Namespace/pod vocabulary throughout | Generalised to workload/environment, so one skill serves every control plane rather than one |

## 4. Trust, security, isolation

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `platform/masking/{detectors,policy,context}.py` | ADAPT | `platform/masking/{detectors,policy,context,mapping,apply}.py` | Reversible identifier masking. Detector *shapes* adopted; every pattern rewritten with bounded quantifiers only, contextual labels required for the generic kinds (FR-004), and a literal prefilter per detector. Upstream has no per-team policy and no `local_models_exempt`. **Landed in 008.** |
| T | `platform/guardrails/{rules,engine,apply,audit,stream}.py` | ADAPT | `platform/guardrails/{rules,engine,audit}.py` | YAML rules, redact/block/audit, span merging. Merge semantics reworked: the representative rule is the widest *individual* contributing match with deterministic tie-breaks, and the action is resolved separately by severity so a wide `audit` cannot neutralise a narrow `block`. Upstream's streaming redactor is not carried over — the equivalent lives in the masking boundary. **Landed in 008.** |
| T | `_MergedSpan` representative-rule semantics | ADAPT | `platform/guardrails/engine.py::merge_spans` | Pinned by a golden suite (SC-004) rather than left implicit; the tie-break chain is new. **Landed in 008.** |
| T | External-surface exception redaction (CWE-209 discipline) | ADOPT | `platform/guardrails/sinks.py` | Two renderings of every failure, produced by different functions rather than one with a flag. Extends `core/llm/redaction.py` from 002 to every sink, with the local CLI explicitly not an external surface (FR-021). **Landed in 008.** |
| — | none — new | — | `platform/masking/llm.py` | The boundary as a decorator over `LLMClient` rather than a change inside the provider layer. Neither upstream masks at a provider-neutral seam; this is what keeps nine adapters from each being the one that forgot, and it holds tokens back across streamed event boundaries. **Landed in 008.** |
| — | none — new | — | `platform/patterns.py` | Load-time validation of any regular expression written outside the repository: structural rejection of an unbounded quantifier inside a repeated group, plus timed probes. Upstream reviews its own patterns by hand; an operator's cannot be. **Landed in 008.** |
| — | none — new | — | `platform/guardrails/rules.py::RulesetLoader` | Hot reload by modification-time poll with last-known-good retention (SC-005), and operator rules merged onto the shipped set *by name* so a file that forgets a rule cannot remove it. **Landed in 008.** |
| — | none — new | — | `platform/trust_controls.py` | Composes both controls and exposes the two ablation switches Article VII requires. "Guardrails off" downgrades every action to `audit` rather than removing the engine. **Landed in 008.** |
| — | none — new | — | `tests/security/test_redos_corpus.py` | Every detector and every shipped rule timed against an adversarial corpus (SC-003). **Landed in 008.** |
| — | none — new | — | `tests/security/test_masking_boundary.py` | Intercepts the outbound document for all nine providers and asserts no unmasked identifier, with a masking-off positive control (SC-001). **Landed in 008.** |
| T | `platform/sandbox/` | ADAPT | `platform/sandbox/profiles/process/` | Local execution policy → `process` profile. Split into `runner`, `execution`, `monitor`, `network`, `limits_posix`, `limits_windows`. The sampler that names *which* bound was crossed and the loopback-only network namespace are new. **Landed in 009.** |
| T | `config/secrets/`, `core/llm/providers/provider_credentials.py` | ADAPT | `platform/credentials/vault.py` | Keyring-backed local secrets → encrypted, versioned vault over `CredentialStore`. Rotation writes a version and moves a metadata pointer rather than overwriting; the vault has no method that returns a value. **Landed in 007.** |
| S | `sre-agent/sandbox_manager.py` (76KB) | ADAPT | `platform/sandbox/profiles/kubernetes/` | Pod-per-investigation, Envoy sidecar egress control, warm pool, TTL, claims. Split into `runner`, `pod_spec`, `envoy`, `warm_pool`, `claims`, `ttl`, `engine`; the monolith is not carried over. Diverges in three ways: the allow-list is derived from `InjectionRule.hosts` rather than written, a claimed instance is destroyed rather than returned to the pool, and JWT injection is not carried over because feature 007 means there is no credential to inject. **Landed in 009.** |
| S | `sre-agent/sandbox-router/sandbox_router.py` | ADAPT | `platform/sandbox/port.py` | Request routing to sandbox instances → folded into the port. A caller holds a `Sandbox` and addresses an instance by handle; there is no separate router to keep in step. **Landed in 009.** |
| S | Credential proxy concept (skills never see secrets) | ADOPT → **mandatory** | `platform/credentials/proxy/` | Upstream treats this as a production mode; NinjaSRE makes it a constitutional invariant in every profile. Split into engine, resolution, injection, egress, refresh, rate limit, audit, and an ASGI mount. **Landed in 007.** |
| S | `sre-agent/sandbox-router/sandbox_router.py` routing | ADAPT | `platform/credentials/proxy/app.py` | Request routing → a two-path internal API on a hand-written ASGI callable. One object serves the `dev` in-process mount and the `standard` service; a test drives both over a real socket and asserts identical behaviour (FR-011). **Landed in 007.** |
| — | none — new | — | `platform/credentials/proxy/signing/sigv4.py` | Proxy-side AWS SigV4. Neither upstream signs outside the client; this is what makes AWS not the exception that would void Article IV (SC-006). Anchored to AWS's published key-derivation example. **Landed in 007.** |
| — | none — new | — | `platform/credentials/proxy/injection.py` | Declarative `InjectionRule` per integration: header, query, path, body, basic, bearer, signature. `hosts` doubles as the egress allow-list, so there is no second list to keep in step. **Landed in 007.** |
| T | `integrations/<vendor>/client.py` patterns | ADAPT | `integrations/_base/client.py` | Retry, pagination, timeouts, rate-limit handling, structured errors — with the credential removed. The base class has no constructor parameter that could accept one. **Landed in 007.** |
| — | none — new | — | `tools/check_direct_credentials.py` | Four CI rules: a credential-shaped env name, any env read from `integrations/`/`capabilities/`, a `CredentialStore` import outside the vault, a `reveal` outside the proxy. Wired into `make verify` (SC-003). **Landed in 007.** |
| — | none — new | — | `tests/security/test_no_credentials_in_agent.py` | The red-team test (SC-001): seed a sentinel, run a real investigation, search environment, filesystem, prompts, tool arguments, transcript, trace, and audit — with a positive control asserting the key *did* reach the vendor. **Landed in 007.** |
| S | `sre-agent/tool_output_sanitize.py` | ADAPT | `platform/guardrails/hooks.py` | Merged into `post_tool_use` scanning rather than kept as a separate sanitiser, so a tool result is filtered before it can become evidence. **Landed in 008.** |
| S | `config_service/src/crypto/` | ADOPT | `platform/persistence/crypto.py` | SQLAlchemy encrypted column types |

## 5. Memory, knowledge, learning

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| S | `sre-agent/memory/models.py` | ADOPT | `platform/memory/models.py` | `Episode`, `Component`, `KeyFinding` — a clean, well-shaped domain model. Renamed `MemoryEpisode` here because the storage port already owns the name `Episode`; `Strategy` lands with feature 011 |
| S | `sre-agent/memory/store.py` | REWRITE | `platform/persistence/repositories/episode_store.py` | Same contract, Postgres + pgvector instead of Neo4j |
| S | `sre-agent/memory/embeddings.py` | ADAPT | `platform/memory/embeddings/` | Pluggable three-member port with a deterministic in-process default, so a no-egress deployment keeps full memory function. Model and width are recorded per vector and a model change is a generation swap, never a write |
| S | `sre-agent/memory/retrieval.py` | REWRITE | `platform/memory/retrieval.py` | `ScoredEpisode` ranking kept; `neo4j-graphrag` replaced with pgvector similarity |
| S | `sre-agent/memory/extraction.py` | ADOPT | `platform/memory/extraction.py`, `platform/memory/effectiveness.py` | Post-turn extraction adopted; the effectiveness heuristic is split out and rewritten as a documented weighted sum with a stored formula version, because it feeds ranking and a prose heuristic cannot be versioned or tested |
| S | `sre-agent/memory/strategy.py` | ADAPT | `platform/memory/strategy/` | **Highest-value single file in S.** The prompt structure and the anti-pattern derivation are retained in intent — four sections, anti-patterns drawn from the runs that failed. Split into a package and hardened: real invalidation, per-key locking, age-based regeneration, component normalisation, operator edits, and an ablation switch. **Landed in 011.** |
| S | `Strategy` model | ADAPT | `platform/memory/strategy/models.py` | Sections and source episode ids kept. Added: `StrategyKey` as a value, `anti_pattern_episode_ids` so FR-003 is checkable rather than asserted, prompt version, date range, staleness, and `OperatorEdit`. **Landed in 011.** |
| S | `StrategyGenerator.get_or_generate` | ADAPT | `platform/memory/strategy/cache.py` | The shape is kept; the caching is rewritten. S regenerated on a bare existence check with no invalidation, no age bound, and no concurrency control — an alert storm produced N playbooks. **Landed in 011.** |
| S | Web console strategy pages | REFERENCE | `platform/memory/strategy/service.py` (`StrategyDirectory`) | Informs feature 021. The read/write API it will sit on — list, read, amend, invalidate, delete — landed in 011; the UI has not. |
| S | `sre-agent/investigation_lifecycle.py` | ADAPT | `platform/memory/lifecycle.py`, `platform/memory/guidance.py` | Split in two: guidance on `on_run_start`, finalisation on `on_run_end`. Exactly-once is enforced twice — an in-process claim for the concurrent-turn race and an upsert by correlation id for the two-process one |
| S | `.claude/skills/memory-search/` | ADAPT | `capabilities/tools/system/memory_search/` | The skill becomes a typed capability with `side_effect_level=read`, a query plus component and issue-type filters, and a result that carries the capability sequence the recalled run used |
| S | `sre-agent/tools/neo4j_semantic_layer.py` | REWRITE | `platform/knowledge/topology/queries.py` | Topology reads reimplemented over the Apache AGE port's closed catalogue. LLM-generated Cypher is gone entirely: no method on the port takes a query string, so there is nothing for a generated one to reach. Transitive *dependencies* are walked in this layer with a visited set, because the catalogue only offers one hop outward and a cycle is legal topology. **Landed in 012.** |
| S | `.claude/skills/infrastructure-neo4j/` | ADAPT | `capabilities/tools/system/topology_query/` | The skill becomes a typed capability with `side_effect_level=read`, returning both directions labelled by what they are for, plus a blast radius with hop distances. Truncation is a sentence rather than a flag, because an operator reading "four affected" when the answer is "at least four" publishes something wrong. **Landed in 012.** |
| S | `scripts/populate_neo4j.py`, `populate_neo4j.cypher` | ADAPT | `platform/knowledge/topology/import_.py`, `topology/discovery/` | A one-shot seeding script becomes a validated declarative document plus three re-runnable discovery adapters. The parser reports every problem at once and refuses an edge naming an undeclared service — in a file that is the source of truth, a typo is a typo. **Landed in 012.** |
| S | `web_ui` knowledge tree / RAPTOR / teaching endpoints | ADAPT | `platform/knowledge/base/` | Hierarchical knowledge base with section-aware chunking, citable retrieval, and a review queue for anything the agent proposes. RAPTOR's summarisation tree is deliberately **not** taken — see the rejections table. **Landed in 012.** |
| S | `.claude/skills/knowledge-base/` (Confluence) | ADAPT | `platform/knowledge/base/sync/confluence.py` | The vendor call moves behind a reader protocol, because tier 3 cannot import an integration. What is left — storage-format body over rendered view, ancestors as the tree, labels as type and tags — is the mapping, and the mapping is the part that is wrong when a citation points at the wrong page. Notion, Google Docs, and a Git working tree are new alongside it. **Landed in 012.** |
| S | Proposed-changes approve/reject flow | ADOPT | `platform/knowledge/proposals.py` | The workflow is adopted; the queue is the platform's own approval store rather than a second mechanism, so Article III's rollback-plan requirement is enforced by the store rather than by this code being careful. **Landed in 012.** |
| T | `tools/system/sre_guidance_tool/` | ADAPT | `config/prompts/knowledge.py` | Methodology surfaced as root-prompt guidance about *when* to search, alongside the knowledge capability rather than as a tool of its own. **Landed in 012.** |
| T | `core/domain/memory/` (files, frontmatter, index, safety, slugs, store) | ADAPT | `platform/knowledge/base/sync/git.py` | File-based notes with frontmatter become operator-authored documents synced from a checked-out repository: the path is the identity, directory index files are the hierarchy, and the directory name sets the document type. A separate `platform/memory/notes.py` is no longer needed — the same documents go through the same ingestion boundary as everything else. **Landed in 012.** |
| T | `core/domain/feedback/misses/` | ADOPT | `platform/memory/misses.py` | Taxonomy of what the agent missed — feeds the evaluation loop |

## 6. Control plane and multi-tenancy

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| S | `config_service/src/core/hierarchical_config.py` | ADAPT | `platform/config_service/{hierarchy,effective}.py` | Org → team tree, ancestry, effective-config computation. Split in two: the tree operations that need the whole shape (deletion guard, reparent, lock-conflict scan) from the resolution path, which reads one indexed chain from `ConfigRepository.ancestors` instead of materialising a tree. **Landed in 013.** |
| S | `config_service/src/core/merge.py` | ADAPT | `platform/config_service/merge.py` | N-level left-to-right deep merge; dicts merge, lists replace. Per-value provenance recorded *during* the merge and lock enforcement folded into it are both new — see the "written fresh" table below. **Landed in 013.** |
| S | `config_service/src/core/config_models.py` | ADAPT | `platform/config_service/schema/` | Six typed sections composed into `RootConfig`, on Pydantic v2 as the plan specifies. `extra="forbid"` is the closed schema; `ValidationError.errors()` is converted to dotted-path `FieldError`s by `schema/types.py`. Pydantic is a runtime dependency rather than an extra: configuration is the one subsystem whose input an operator writes, and a deployment that could not validate a document would resolve to defaults nobody chose. **Landed in 013.** |
| S | `config_service/src/core/default_prompts.py` | ADAPT | `config/prompts/` (already there) | Defaults stay code constants; only overrides are configuration, so a fresh deployment works with no configuration and a prompt improvement is a diff rather than a migration. **Landed in 013.** |
| S | `config_service/src/core/{config_cache,cache}.py` | ADAPT | `platform/config_service/effective.py` | Bounded LRU. **Deviation from plan, and the only one:** keyed on the ancestor chain's own `ConfigNode.version` values rather than a hand-maintained hierarchy counter. The plan's counter is correct only while one process does all the writing; a fingerprint read from the row stays correct with a console, a scheduler, and three API replicas writing at once, and invalidates per branch rather than globally. **Landed in 013.** |
| S | `config_service/src/core/{skills_catalog,tools_catalog}.py` | ADAPT | `platform/config_service/catalogue.py` | Capability catalogue exposed to the console. Reworked into two protocols because this is tier 3 and the registries are tier 2; `CatalogueView` carries an unavailability *reason* per capability, which neither upstream had. **Landed in 013.** |
| S | `config_service/src/core/integration_config.py` | ADAPT | `platform/config_service/schema/integrations.py` | Vault references and non-secret settings only. The credential fields are removed rather than ignored. **Landed in 013.** |
| S | `config_service/src/core/dependency_validator.py` | ADAPT | `platform/config_service/validation.py` | Cross-reference against the live catalogue at write. Secret-shaped rejection through the guardrail engine is new. **Landed in 013.** |
| S | `config_service/src/core/{yaml_config,yaml_validator,yaml_seeder}.py` | ADAPT | `platform/config_service/templates/engine.py` | Template loading and application. Diff-before-apply is new; the preview and the application are the same `deep_merge`, so they cannot disagree. **Landed in 013.** |
| S | `config_service/src/core/audit_log.py` | ADAPT | `platform/config_service/audit.py` | One row per changed *field*. Guardrail filtering of audited values, and auditing a refused write without its value, are new. **Landed in 013.** |
| S | `config_service/src/api/routes/{admin,auth_me,sso,team,audit,security}.py` | ADAPT | `gateway/http/security/route_permissions.py` | The routes themselves land with feature 020; what landed in 014 is the *declaration* of each one and the permission it needs. S decorated handlers; the table is the source a handler is wired from, so an undeclared route cannot obtain a guard. **Landed in 014.** |
| S | `config_service/src/core/admin_rbac.py` | ADAPT | `platform/identity/{permissions,authorisation}.py` | S had a flat role→permission dict checked inside services. Split in two: a catalogue built by accumulating increments (so the nesting is a property of the construction rather than of five hand-written sets) and node-scoped resolution against the configuration hierarchy. **Landed in 014.** |
| S | `config_service/src/core/oidc.py` | ADAPT | `platform/identity/{oidc,sso_config}.py` | Authorization Code with PKCE, claims, group→team mapping. S's flow did its own HTTP; ours is pure functions over values with the transport outside, which is what lets test-before-activate run the same code the live flow runs. **Landed in 014.** |
| S | `config_service/src/core/security.py` | ADAPT | `platform/identity/{tokens,sessions}.py` | Token issue/hash/verify and session handling. S stored a bare SHA-256; ours is a keyed hash so a database dump is not a set of working credentials. Clock-skew tolerance on expiry — and deliberately *not* on revocation — is new, as are the inactivity and expiry-warning policies. **Landed in 014.** |
| S | `config_service/src/core/impersonation.py` | ADAPT | `platform/identity/impersonation.py` | S's was time-limited and audited. The refusal to start without a written reason, and checking the permission *at the impersonated node* rather than organisation-wide, are new. **Landed in 014.** |
| S | `config_service/src/core/audit_log.py` | ADAPT | `platform/identity/audit/recorder.py` | Second use of the same upstream (the first was 013's config auditor). Here it gains the acting-context model — attribution merged after the caller's payload so it cannot be forged — plus the durable fallback and alert on write failure. **Landed in 014.** |
| S | token audit, expiry, and bulk-revocation flows | ADOPT | `platform/identity/tokens.py` | Ported with the bound added: 500 per call, because one statement that could revoke a deployment is not a control. **Landed in 014.** |
| S | `config_service/src/api/auth.py` | ADAPT | `gateway/http/security/dependencies.py` | S's dependency resolved the principal and checked the role in one function. Split: the transport resolves, the guard decides, and the guard is a plain callable so a permission decision is testable without a server. **Landed in 014.** |
| S | `config_service/src/db/` + `alembic/` | ADAPT | `platform/persistence/` | Models and migrations, extended for the unified store |
| S | `config_service/src/api/routes/scheduled_jobs.py`, `db/scheduled_jobs.py` | ADAPT | `platform/scheduler/` | Recurring investigations |
| S | `config_service/golden_templates/` (10 use-case configs) | ADOPT | `platform/config_service/templates/golden/` | Consolidated to seven: Slack triage, CI failure, cost, postmortem, alert fatigue, DR validation, observability advisory. Beside the code rather than in `deploy/`, matching `guardrails/defaults/rules.yml` — an operator forks one and points at their own directory. **Landed in 013.** |
| T | `platform/scheduler/` | ADAPT | `platform/scheduler/` | Claim store, executor, concurrency — merged with S's job model |
| T | `platform/auth/` | REFERENCE | — | Superseded by S's fuller identity layer. Confirmed at 014: its JWT helpers assumed a hosted issuer. |
| T | Clerk integration | REJECT | — | A hosted identity SaaS. Article X: the operator owns their data, and their directory is theirs. |
| T | `gateway/billing/`, Clerk dependencies | REJECT | — | Hosted-SaaS concerns; NinjaSRE is self-hosted only |

## 7. Action governance

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `core/tool_framework/metadata.py` (`SideEffectLevel`, `requires_approval`) | ADOPT | `core/capability/metadata.py` | Declarative side-effect classification is the foundation of Article III |
| T | `gateway/runtime/approvals.py`, `gateway/{slack,discord}/approvals.py` | ADAPT | `platform/approvals/routing.py`, `platform/approvals/closure.py`, `platform/approvals/notification.py` | Inline approval in the surface the human is already using. **Shipped in 015.** The reviewer set is *derived* from node-scoped grants rather than configured, and closure is one event every surface subscribes to rather than per-surface state |
| S | `config_service/src/api/routes/remediation.py`, web console remediation review/rollback | ADAPT | `platform/remediation/request.py`, `platform/remediation/rollback/executor.py` | **Shipped in 017.** 015 shipped the renderer and the side-effect gate; 017 adds the request assembly, the pre-execution plan, and the rollback executor. The upstream's rollback endpoint applied whatever was recorded; the target-match refusal has no upstream |
| S | Pending-changes review flow (`proposed-changes/*/approve\|reject`) | ADAPT | `platform/approvals/models.py`, `platform/approvals/state_machine.py`, `platform/approvals/service.py` | **Shipped in 015.** Adapted rather than adopted: the upstream had no conflict detection, no decision-time permission re-check, and no blast radius, and its state set had no `conflicted` |
| S | `config_service/src/api/routes/security.py` `SecurityPolicy` model | ADOPT | `platform/approvals/policy.py` | **Shipped in 015.** The field set is the upstream's; the enforcement is not (see below) |
| T | `platform/guardrails/` | REUSE | `platform/approvals/diff/engine.py` | Every rendered diff value passes the engine before display and before the audit record |
| S | `.claude/skills/remediation/scripts/{restart_pod,rollback_deployment,scale_deployment}.py` | ADAPT | `capabilities/tools/remediation/{restart_workload,rollback_deployment,scale_workload}/` | **Shipped in 017.** Three shell scripts become three packages of four components each. The upstream scripts performed the action; these refuse their own invocation and route through the gate |
| S | `runtime-config-flagd` skill | ADAPT | `capabilities/tools/remediation/toggle_feature_flag/` | **Shipped in 017.** The upstream toggled a value; this records the rollout percentage as well, because restoring the value alone turns a partial rollout into a full one |

## 8. Surfaces

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `surfaces/cli/` | ADAPT | `surfaces/cli/` | **Shipped in 019.** Command structure, onboarding wizard, integration setup |
| T | `surfaces/interactive_shell/` | ADAPT | `surfaces/repl/` | **Shipped in 019.** REPL with slash commands, streaming UI, session control |
| T | `surfaces/interactive_shell/command_registry/` | ADAPT | `surfaces/repl/commands/registry.py` | **Shipped in 019.** Registry-generated `/help`; the local-only execution guarantee is stated as a property of the context rather than a convention |
| T | `surfaces/interactive_shell/ui/` | ADAPT | `surfaces/cli/output/`, `surfaces/repl/streaming.py` | **Shipped in 019.** Streaming, tables, layout, degradation. Split so the CLI and the REPL share one degradation decision |
| T | `surfaces/interactive_shell/AGENTS.md` action-selection rule | ADOPT | `surfaces/repl/AGENTS.md`, `surfaces/repl/routing.py` | **Shipped in 019.** The no-intent-routing prohibition, adopted verbatim in substance and enforced by a test battery of lines a keyword router would have claimed |
| T | `tools/interactive_shell/actions/` | ADAPT | `surfaces/repl/commands/` | **Shipped in 019.** Capability-driven actions become the sixteen slash commands |
| T | `platform/terminal/` | ADAPT | `surfaces/cli/output/degradation.py` | **Shipped in 019.** Terminal capability detection: colour, Unicode, width, pipe |
| T | `install.sh`, `install.ps1` | ADAPT | `install/install.sh`, `install/install.ps1` | **Shipped in 019.** Rebranded, telemetry removed, integrity verification retained and moved ahead of unpacking |
| T | Homebrew tap | ADAPT | `install/homebrew/ninjasre.rb` | **Shipped in 019.** The package-manager path for operators who will not pipe a script to a shell |
| T | `gateway/{slack,telegram,discord}/` | ADAPT | `gateway/slack/`, `gateway/telegram/`, `gateway/discord/` | **Shipped in 022.** Transport, approvals, thread history, output sinks — reworked so the behaviour lives once in `gateway/chat/` and each of these is a payload builder |
| T | `platform/notifications/` (cooldown, redaction, limits, delivery) | ADOPT | `platform/notifications/` | Delivery discipline: cooldown and redaction at the sink |
| T | `tools/investigation/reporting/` | ADAPT | `platform/reporting/` | Formatters, renderers, delivery registry, upstream correlation |
| S | `web_ui/` (Next.js, ~33k LOC TS) | ADAPT | `surfaces/console/` | Investigations, transcript, memory hub, config editor, org tree, approvals, trace replay |
| S | `teams-bot/` | ADAPT | `gateway/teams/` | **Shipped in 022.** Bot Framework wiring, Adaptive Cards, in-place card streaming, the identity flow |
| S | Slack Socket Mode bot | REFERENCE | — | **Confirmed in 022.** T's Slack gateway is more complete; S's SSE contract informs the event protocol. Both ingress modes shipped, converging on one handler |
| S | `sre-agent/events.py` | ADOPT | `gateway/http/events.py` | SSE event protocol: `thought`, `tool_start/end`, `task_started`, `background_waiting`, `message_queued`, `question`, `result`, `error` |
| — | Pushover | NEW | `platform/notifications/sinks/pushover.py` | Requested addition; no upstream equivalent |

## 9. Integrations

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `integrations/<vendor>/` × 76 | ADAPT | `integrations/<vendor>/` | Consistent anatomy: config normalisation, `verifier.py`, `client.py`. Credential access rerouted through the proxy |
| T | `integrations/verification/` | ADOPT | `integrations/_verification/` | Connectivity verification framework |
| T | `integrations/hermes/` | ADAPT | `integrations/hermes/` | Log tailing, incident classification, correlator |
| T | `core/tool_framework/utils/mcp_*.py`, `integrations/openclaw/` | ADAPT | `capabilities/protocols/` | MCP bridge, ACP, OpenClaw |
| S | 51 skills' client modules | ADAPT | merged into `integrations/<vendor>/client.py` | Where both projects cover a vendor, T's client is the base and S's methodology becomes the skill |
| T | `integrations/posthog/`, `integrations/posthog_mcp/` | ADAPT | `integrations/posthog/` | Kept as a *user* integration; removed as internal telemetry |

## 10. Evaluation

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `tests/synthetic/schemas.py` | ADOPT | `tests/synthetic/schemas.py` | Fixture schemas and validators — the contract that keeps 72+ scenarios consistent |
| T | `tests/synthetic/{eks,rds_postgres,grafana,hermes,openclaw,...}/` | ADOPT | `tests/synthetic/` | 72 scenarios with `scenario.yml` + `answer.yml` ground truth |
| T | `tests/synthetic/mock_*_backend/` | ADOPT | `tests/synthetic/backends/` | Mock AWS, Datadog, EKS, Grafana, Hermes, OpenClaw |
| T | `tests/synthetic/score_artifacts.py` | ADOPT | `tests/harness/scoring/artifacts.py` | Per-attempt JSONL verdicts |
| T | `tests/benchmarks/cloudopsbench/` | ADAPT | `tests/benchmarks/cloudopsbench/` | External benchmark adapter |
| T | `tests/benchmarks/toolcall_model_benchmark/` | ADAPT | `tests/benchmarks/models/` | Cross-model comparison |
| T | `tests/chaos_engineering/` | ADOPT | `tests/chaos/` | Chaos Mesh experiments: container-kill, dns-error, http-abort, io-latency, network-delay/corrupt/bandwidth |
| T | `tests/e2e/` | ADAPT | `tests/e2e/` | Cloud-backed scenarios across K8s, EC2, CloudWatch, Lambda, ECS Fargate, Flink, Airflow, Jenkins, GitLab |
| S | `test-infra/{eks,kind}/`, otel-demo + flagd fault injection | ADOPT | `tests/e2e/otel_demo/` | Reproducible fault injection via feature flags — excellent for CI |
| S | `scripts/{eval_agent_performance,run_agent_eval,fault_analysis}.py` | ADAPT | `tests/harness/eval/` | Agent performance evaluation |
| — | Ablation harness | NEW | `tests/harness/ablation.py` | No upstream equivalent. Required by Article VII |
| — | Trajectory scorer with golden-trajectory matching | ADAPT from T `answer.yml` schema | `tests/harness/scoring/trajectory.py` | The schema exists upstream; a general scorer implementation does not |

## 11. Engineering practice

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `.importlinter`, `.importlinter.strict` | ADOPT | `.importlinter` | CI-enforced layer boundaries — the single most valuable process artifact in either repo |
| T | `AGENTS.md` (30KB) | ADAPT | `AGENTS.md` | Code style, file placement policy, CodeQL footguns. Repo-specific parts rewritten |
| T | `docs/NAMING.md`, `docs/tool-placement-policy.md` | ADAPT | `docs/conventions/` | Naming and placement rules |
| T | `CI.md`, `Makefile`, `ruff.toml`, `mypy.ini`, `pytest.ini` | ADAPT | root | Toolchain: `uv`, `ruff`, `mypy`, `pytest` |
| S | `ruff.toml`, `docker-compose.yml`, `Makefile` | REFERENCE | `deploy/compose/` | Compose topology informs the standard profile |
| T | `.github/workflows/`, `.github/codeql/` | ADAPT | `.github/workflows/` | CI including CodeQL |

## 12. Explicit rejections

| What | From | Why |
|---|---|---|
| PostHog + Sentry opt-out telemetry | T | Constitution Article X — no off-host transmission |
| Clerk auth, billing/credits, hosted gateway concerns | T | Self-hosted only; superseded by S's identity layer |
| `opensre-infra-aws` deployment automation, Cloudflare install proxy | T | Vendor-specific hosted infrastructure |
| Neo4j as datastore | S | Constitution Article XI — single Postgres |
| Claude Agent SDK as primary runtime | S | Constitution Article V — canonical runtime must be first-party |
| Dual `server.py` / `server_simple.py` split | S | One API layer; isolation is a deployment profile |
| Direct `Bash` execution of skill scripts against production | S | Constitution Article IX — capabilities must be typed and plannable |
| LangChain / `langchain_neo4j` dependency | S | Replaced by direct parameterised graph access |
| Graph/chain framework layers | T (already removed upstream) | Confirmed dead end by upstream's own refactor |
| S's RAPTOR summarisation tree | S | A tree of LLM-written summaries of summaries is a corpus of text nobody wrote, retrieved as though somebody had. A passage returned from level three of it cannot be cited, because there is no document it came from — and a runbook the agent cannot cite is one it paraphrases. Chunks are cut from the operator's own text and nothing else. |
| S's LLM-generated Cypher | S | An injection surface and a correctness problem at once: a traversal nobody bounded returns the whole estate, slowly, and the query text arrives from a model that has been reading production output. The nine-shape catalogue covers the investigative need and there is no way to phrase anything else. |
| Auto-applying agent-proposed knowledge | S | An agent that writes knowledge it later reads, unreviewed, builds a self-reinforcing belief system with no external correction. Human review is the only available loop breaker, and SC-007 asserts there is no path around it by attempting one. |

### Feature 010 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `platform/memory/policy.py` | Neither upstream could ablate memory. Article VII makes it non-optional, and reading and writing switch separately so the experiment worth running — a populated corpus the agent may not consult — is one the harness can express. |
| `platform/memory/ranking.py` | S ranked inside its retrieval query. Pulling the weights out into a versioned formula with a golden ordering test is what makes a weight change reviewable rather than a silent reinterpretation of the corpus. |
| `platform/memory/embeddings/local.py` | S embedded through a hosted model on every write and every recall, which breaks the no-egress deployment that motivates the product. |
| `platform/memory/purge.py` | Deleting an episode and its vector in one unit of work has no upstream; S left the index to drift. |
| `RecallLedger` in `platform/memory/retrieval.py` | Recording whether the agent *acted on* a recall is what turns "memory helps" into a number. Neither upstream recorded it. |

### Feature 011 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `platform/memory/strategy/normalisation.py` | S keyed strategies on the raw component name, which is why its playbooks rarely triggered: `payments`, `payments-api`, and `payments-7f9dd-x7gr9` are three keys with two episodes each and the threshold is never reached. The rules here are new, and so is the deliberate timidity — a wrong merge produces a confidently misleading playbook that nothing downstream can detect, so anything the rules do not cover needs an operator's alias. |
| `platform/memory/strategy/invalidation.py` | S had no invalidation at all. Marking on the episode write, in the same unit of work, using the same normaliser as the read side, is the whole of what makes the cache a cache of something. |
| `platform/memory/strategy/policy.py` | Neither upstream could ablate playbooks. It is a third switch rather than a mode of the two memory switches, because the question is "do playbooks help, given the episodes were already there" and folding it into the read switch would make the baseline a run with no memory at all. |
| `KeyedLock` in `platform/memory/strategy/cache.py` | S generated per request. The per-key lock with a re-read for the losers is new; the cross-process half of the guarantee comes from the primary-key upsert on the row. |
| `OperatorEdit` preservation | S's console could edit a playbook and the next regeneration overwrote it. Carrying edits across regeneration, marked and attributed, is new. |
| `STRATEGY_PROMPT_VERSION` on the stored playbook | S had no prompt version. Without it a prompt edit silently reinterprets every cached playbook and no one can attribute the quality shift. |
| `tests/synthetic/test_strategy_value_scenario.py` | Neither upstream measured whether a playbook changed a trajectory. SC-005 is that measurement. |

### Feature 009 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `platform/sandbox/port.py` | Neither upstream had one port over three profiles. Streaming as the primitive with `execute` derived from it, and the terminal-event contract, are the reason the contract suite can be one suite. |
| `platform/sandbox/spec.py` | `EgressPolicy.from_injection_rules` ties the sandbox's allow-list to the credential proxy's. Neither upstream had a proxy to tie it to. |
| `platform/sandbox/content.py` | S baked skills into the sandbox image. Immutable delivery with a digest verified before every execution is new, and is what makes FR-020 checkable in all three profiles by one assertion. |
| `platform/sandbox/profiles/container/` | Neither upstream had a container profile: T ran locally, S required a cluster. |
| `platform/sandbox/reaper.py` | S reaped by TTL. Lease-based orphan detection against a set of live runs is new, and is what turns a killed agent into one sweep's cleanup. |
| `platform/sandbox/selection.py` | Reporting what a profile enforces *on this operating system* has no upstream. It is what makes the light profiles defensible rather than merely convenient. |

### Feature 012 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `platform/knowledge/topology/reconciliation.py` | S seeded its graph with a script and re-seeded by replacing. The three-way merge is new, and the row that earns it is the degraded-source path: a control plane having a bad minute reports a third of the estate, and replace-on-discovery reads the missing two thirds as retired. The symptom arrives days later as a blast radius that is quietly wrong. |
| `edges_from` / `delete_edge` on `TopologyGraph` | Two shapes added to the port deliberately, because every traversal returns *nodes* and reconciliation has to read what is on an edge — the operator's annotation, and whether a human drew it. A soft delete written through `upsert_edge` would not work either: a retired edge still leads a node-returning traversal to the node behind it. |
| `platform/knowledge/topology/discovery/port.py` | The three-outcome health signal has no upstream. Collapsing "saw part of the estate" into either "saw it" or "could not run" is the bug FR-008 exists to prevent, and the port is where the three are made distinguishable. |
| The noise floors in `discovery/mesh.py` and `discovery/traces.py` | Neither upstream had observational discovery. A stray health probe becomes a dependency the agent reasons about and nobody has — and unlike a missing edge, a wrong one is not obviously wrong when you read it. |
| `platform/knowledge/base/chunking.py` | S chunked into a RAPTOR tree. Section-aware cuts with overlap, and offsets into the original body, are new — the offsets are what let a rejected document report *where* its secret was without quoting it. |
| Ingestion refusing rather than redacting | Neither upstream screened documents at all. Refusal is the deviation worth recording: it holds even in guardrail audit-only mode, because that ablation is reversible run to run and a corpus permanently holding a credential is not. |
| `platform/knowledge/policy.py` | Neither upstream could ablate either store. Two independent switches, because "is it worth populating the graph" and "is it worth writing the runbooks" are two questions and one switch answers neither. |
| `TopologyLedger` and `KnowledgeLedger` | Recording every query and whether the run went on to cite it is what turns "topology helps" into a number. Neither upstream recorded either. |
| `tests/benchmarks/test_topology_scale.py` | SC-001 at this layer rather than at the port's. One of the two proves the traversal bounds its own walk; the other proves the backend does. |

### Feature 013 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| Per-value provenance in `merge.py` | S merged and returned values. Recording the source node *during* the merge is new, and it has to be during: the type-mismatch cases — a scalar replacing a subtree, a subtree replacing a scalar — are where a reconstruction after the fact gets it wrong, and the failure mode is a provenance table that is confidently wrong rather than merely incomplete. |
| Lock enforcement inside the merge | S enforced locks at the write only. Enforcing again at read is what makes "a locked field cannot be overridden at any depth" true regardless of how a value reached storage — a restored backup, a lock added after the fact, a direct database write. It skips rather than raises, because a resolution that refused would be an incident that cannot be investigated. |
| The stored envelope in `document.py` | S kept field policies alongside settings. Separating them is what makes "the merge interprets nothing" achievable at all: a policy inside the settings is a control key, and one control key is the beginning of a configuration language. |
| The closed field set (`extra="forbid"` on every section) | Neither upstream rejected an undeclared key. A typo in a field name is otherwise a setting that is stored, rendered in the console, and never read — and nothing in the system can tell that apart from a field that works. |
| The salvage pass in `RootConfig.read` | Pydantic validates a document whole, so one bad field would take every good one with it. The resolution path must never raise — refusing to resolve is refusing to investigate an incident — so `read` prunes the failed paths and revalidates, and a bad entry inside a list drops the entry rather than the list. Neither upstream had a non-raising read path at all. |
| `ConfiguredInt` rejecting a boolean | Pydantic's lax mode reads `True` as `1`, which would turn `tool_budget: true` into a budget of one. The string coercions are left lax on purpose: a hand-written template says `on` and `8` at least once and both are unambiguous. |
| Secret-shaped rejection in `validation.py` | Neither upstream screened configuration values. `REFERENCE_FIELD_NAMES` is the non-obvious part: scanning `credential = datadog-prod` with its own label attached fires the generic labelled-secret rule on the field that exists precisely so the secret is elsewhere. |
| Auditing a *refused* write | New, and the reason is the ordering: the write failed, so a shared transaction would roll the record back with it. It is written in its own transaction, with the path and the reason and never the value. |
| Replacing rather than redacting an audited value | Stricter than the guardrail engine's own redaction, because the engine downgrades to observe-only under the ablation switch and an audit row is append-only and retention-exempt. A filter that an unrelated switch could turn off would be the one route by which a rejected credential outlives the rejection. |
| `bindings.py` | Neither upstream had ablation switches to bind. One module rather than a method per subsystem, because the property worth protecting is that all of them derive from *one* resolution — wiring them separately is how a deployment ends up with topology switched off in the query path and the guidance paragraph still telling the agent to query the graph. |
| Cache keyed on chain row versions | S invalidated by clearing. The fingerprint approach is new and is what makes invalidation correct with a console, a scheduler, and three API replicas all writing. |
| `tests/benchmarks/test_config_resolution.py` | SC-003. Neither upstream measured resolution, and the cost sits on the investigation path once per run — the kind of few hundred milliseconds nobody attributes to configuration. |

### Feature 014 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `gateway/http/security/route_permissions.py` as the *source* of guards | S decorated handlers and kept no list; T had no permission model worth the name. A checklist compared against a mounted router is a second list kept in step by hand, and the day it falls behind is the day it reports that an unguarded route is guarded. Making the table the thing a handler is wired *from* is what turns SC-001 into a wiring failure instead of a review comment. |
| The nesting of the five roles, and its construction | S's roles overlapped without containing each other, so every denial needed a matrix lookup. Building them by accumulating increments — rather than writing five complete sets — makes the containment a property of the code rather than of somebody's discipline, and it is what lets a denial answer "you need the next role up". |
| Node-scoped grants resolving against the configuration hierarchy | S scoped roles to a team id, one level. Reusing the config tree is new and is the point: two scoping models would give an operator two mental models, and the one they got wrong would be the security one. Denying on an unknown node — rather than falling back to the root — is the half that is a security property. |
| `require_owner_retained` evaluating the whole change | Neither upstream protected the last owner at all. Per-removal checking gets both interesting cases wrong: it refuses a legitimate one-step handover, and it permits removing every owner in one call. |
| `platform/identity/audit/guard.py` | An executable form of "no repository may edit the audit log", run at startup. Neither upstream had one; S's audit table was an ordinary table an admin could `UPDATE`. |
| The append-only database trigger (`postgres/audit_guard.py`, migration 0003) | The layer that survives a refactor, an ORM, and a `psql` prompt. `FOR EACH STATEMENT` rather than per row, so a delete matching nothing is refused too — an operator learning their delete was rejected only when it happened to match something is an operator who believes audit rows are deletable. |
| The durable audit fallback (FR-028) | Neither upstream did anything when an audit write failed. A file, because the fallback has to work in exactly the situation the datastore does not; NDJSON, because that is the state the file is most likely to be found in; the same record shape as the export, so what an operator recovers merges with what they archived. |
| Test-before-activate binding a result to a fingerprint | S could test a provider. Binding the result to the exact settings that produced it is new, and without it an operator tests a working configuration, edits the client id, and activates on the strength of the old result. |
| Break-glass as a first-class, reason-carrying path | S had a local admin with no time limit and no distinct audit. Fifteen minutes, a mandatory written reason, an error-level log line for a *successful* sign-in, and scrypt rather than the token hasher — the last because this is a passphrase a human types and the whole defence is the cost per guess. |
| `ApiToken.{team_node_id,description,last_used_at}` and the port methods around them | Added to the persistence port deliberately. Without `team_node_id` a token is as wide as its owner; without `last_used_at` an inactivity policy is inexpressible. The coarse write-back — a row per token per day, not per request — is what stops it becoming the busiest column in the deployment. |
| `TokenDirectory.find_token_by_hash` | `resolve_token` refuses to say *why* a token failed, which is right on the authentication path and is also why a rejected attempt would otherwise have no tenant to be recorded against. One method, for the audit row only, documented as never authenticating. |
| `attribution` as a plain mapping on `ConfigAuditor` | The identity layer already imports the config hierarchy, so config cannot import identity back. Passing the impersonation keys as data rather than as a type keeps the record complete and the dependency pointing one way. |
| `tests/security/test_impersonation_audit.py` parameterised over `AUDITED_ACTIONS` | Neither upstream asserted the dual-principal property at all, let alone across every action class. A trail with one gap is a trail an admin can act through, so the assertion has to iterate the vocabulary rather than sample it. |

### Feature 015 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| Conflict detection by target-state fingerprint (`models.fingerprint_of`, `service._require_unconflicted`) | Neither upstream had any. S's pending changes applied whatever was queued, against whatever the target said at the moment somebody clicked. That is the specific way approval workflows produce incidents: a reviewer approves a diff describing a world that no longer exists, and the failure is attributed to them for doing exactly what they were asked. |
| Sibling conflict on approval (FR-009) | S applied each queued change to the same target independently, last write winning. Marking the rest conflicted rather than applying or discarding them is what keeps each author entitled to re-review their own proposal against what the target says now. |
| Decision-time permission re-checking (`service._require_permitted`) | Both upstreams checked at queue time only. Offboarding between the queue and the decision is the ordinary case, not the edge one, and queue-time-only checking leaves a departed employee with latent authority over production configuration. |
| Self-approval refused *through impersonation* | S had a self-approval flag and checked the presented principal. Checking the real principal as well is what makes it a control rather than a speed bump: an admin who steps around it by acting as the requester has stepped around it. |
| `conflicted` as a fifth, **non-terminal** state | Both upstreams had pending/approved/rejected. A conflicted change that was terminal would mean an operator's edit disappeared because a colleague touched a neighbouring field; making it reachable back to `pending` is what turns detection into re-review. |
| Summarisation with drill-down rather than truncation (`diff/summarise.py`) | Neither upstream did anything for a large diff. A truncated diff looks exactly like a small one, so the reviewer approves what they were shown and the rest applies unread. The summary states that it is one, how much it omitted, and how to expand it — and `SC-008` asserts it against ten thousand lines. |
| Blast radius through configuration inheritance (`blast_radius.py`) | New. S showed which node a change was made at and nothing about who inherits from it. The exclusion of overriding descendants is the half that keeps the number meaningful, and `known=False` for an unreadable tree exists because "nothing beneath it" is the one reassurance an absent input must not give. |
| Policy enforcement that takes no principal (`SecurityPolicy.check_settings`) | S's policy was enforced in route handlers that had the caller's role in hand, so an owner path could and did skip it. Taking settings and nothing else makes the absence of an exemption a property of the signature, which is what `SC-006` asserts and what `test_the_policy_check_takes_no_role_at_all` pins. |
| `PolicyChangeEffect` and its two always-empty fields | FR-018 in a value rather than a paragraph. Neither upstream said anything about what a policy change did to queued work, so each surface guessed. `applied_automatically` and `discarded_automatically` are on the value *because* they are always empty: a console can state the guarantee from the data. |
| One mechanism for five change types | S had three review flows — config, knowledge, remediation — with three state sets and three audit shapes. Unifying them is the feature. The change type decides three things only: which renderer runs, which applier applies, and whether policy gates it. |
| `ApprovalStore.amend_request` (added to feature 006's port) | A review that outlives the state it was raised against has to record that, and be re-raised, without either being a decision. The port had `create` and `decide` and nothing in between, so a conflict mark had no home. Refused on a decided request, so the append-only property of a *decision* is untouched. |
| `GatedChangeQueue` declared by the configuration service | The dependency has to run one way — the approval layer needs the hierarchy for a blast radius, so configuration cannot import it back. A protocol declared by the caller and implemented by `approvals.appliers.ApprovalQueueAdapter` keeps the graph a graph, and `test_the_configuration_service_does_not_import_the_approval_layer` asserts it. |
| The structural half of SC-001 | `test_only_the_service_can_put_a_change_into_approved` parses the package's own source and refuses any module outside the service and the state machine that can *produce* `ChangeState.APPROVED`. The behavioural half proves today's code is right; this is what notices the shortcut somebody adds next year. |

### Feature 017 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| The ordering as the specification (`gating.decide`) | Neither upstream had one. S's remediation route approved and applied in the same call; T's approval gate had no rollback obligation at all. Kill switch, then allow-list, then approval, then **plan persisted**, then re-evaluation, then execute — each step is somewhere a change can be stopped, and having them in one function is what makes "every entry point" true rather than aspirational. |
| Two snapshots on a rollback plan (`RollbackPlan.{recorded_state,applied_state}`) | New, and the mistake it prevents was made during this feature's own construction: checking a rollback against the *pre*-execution state refuses every legitimate undo, because the action's whole effect is that the target no longer looks like that. The code reads plausibly either way, which is exactly why the distinction is a field rather than a comment. |
| `StateSnapshot.unreadable` as a distinct value | S's remediation read returned an empty dictionary when the control plane was down. An empty snapshot fingerprints to a real value and compares equal to another empty one, so a rollback would proceed against a target nobody could read. `known=False` matches nothing, including itself. |
| Condition re-evaluation at execution time (`autonomy/evaluation.py`) | Neither upstream had autonomy at all. The evaluator holds no result and offers no way to reuse one, because the failure this exists to prevent is a condition answered when an action was proposed and reused ten minutes later against a system that has moved. |
| An unknown blast radius failing a ceiling | New. The gate feeds a deliberately enormous number when the topology graph cannot answer. The alternative is an allow-list that silently widens itself the day the graph extension is uninstalled. |
| Partial-success scoping (`RollbackPlan.scoped_to`) | S recorded a remediation as succeeded or failed. Three of five instances restarted is the ordinary outcome of acting on a live system, and a plan still covering five is an instruction to change two things nobody touched — an unreviewed change under the authority of a reviewed one. |
| Post-execution verification (`verification.py`) | Neither upstream read the target back. "The API returned 200" and "the change took effect" are different claims, and a control plane that accepts a scale it cannot schedule reports the first while the second is false. Divergence is reported and never repaired: re-applying would be a second unapproved action, and the one it would take has already failed once. |
| The kill switch (`autonomy/kill_switch.py`) | New. Neither upstream had an emergency stop. State is never cached and scopes nest, because the window in which a cached switch still lets a write through is measured in exactly the seconds it exists for. |
| `RemediationApplier.apply` doing nothing, deliberately | For the other four change types approval *is* the change. For a remediation, three steps stand between the decision and the action — re-evaluation, the target lock, the sandbox — and S's route collapsed all three into the approval call. |
| A capability function that refuses itself | S's scripts performed the action when invoked. A capability that can be invoked directly is one that can run with no approval, no plan, and no sandbox, so all seven refuse and name the gate. The no-unapproved-write test walks the catalogue rather than a list. |
| `clear_cache` shipped with no derivable plan | Deliberate. A waiver path only the untestable capabilities used would be one nobody had ever run, and the first time it is needed is during an incident. |

### Feature 018 — what came from where

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| S | `AskUserQuestion` SDK pattern, `question` SSE event | ADAPT | `core/agent/handoff.py`, `capabilities/tools/system/ask_human/` | **Shipped in 018.** Structured options and a stated reason are the upstream's shape. The credential refusal at the boundary and the guardrail screen on the answer are not — the upstream could be asked for anything |
| S | `sre-agent/message_queue.py` | ADAPT (via 004) | `core/agent/message_queue.py` | Feature 004 shipped the debounce and the merge. 018 adds surface attribution, guardrail screening on submit, and the merge receipt |
| S | Mid-run `queue-message` endpoint, `message_queued` event | ADOPT | `core/agent/message_queue.py` (`MergeReceipt`, `ReceiptSink`) | **Shipped in 018.** The event is the upstream's; emitting it at the *merge* rather than at the submit is not — "we have it" and "the agent has read it" are different facts, and only the second stops somebody typing it again |
| S | `sre-agent/server.py` interrupt endpoint | ADAPT | `core/agent/takeover.py`, `ReActLoop.pause` | **Shipped in 018.** The upstream interrupted; this pauses, reaps, records under the human principal, and resumes into the same trace |
| T | `gateway/runtime/attention.py` | ADOPT | `core/agent/interaction/attention.py` | **Shipped in 018.** The idea that a run listing has to say which runs are blocked. Derived from open interactions rather than stored as a flag |
| T | `gateway/runtime/approvals.py` cross-surface handling | ADAPT | `core/agent/interaction/closure.py` | **Shipped in 018.** 015 adapted this once into `platform/approvals/closure.py`; 018 generalises it to the supertype and makes the approvals version a shell over it |
| T | Interactive-shell cancellation semantics | REFERENCE | — | Informs the takeover pause path: stop between iterations, never mid-call |
| T | `platform/notifications/` cooldown discipline | REUSE (pattern) | `core/agent/interaction/progress.py` | The cooldown-at-the-sink idea, applied to progress reporting before feature 023 exists to hold the transport |

### Feature 018 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `Interaction` as a supertype of question and approval | Neither upstream had one. S had a question flow and a pending-changes flow with nothing in common; T had approvals with cross-surface closure and questions without it. Unifying them is what makes persistence, first-writer-wins, and attention exist once rather than twice — and it is the specific asymmetry both upstreams shipped |
| First-writer-wins as a conditional transition returning a value (`registry.resolve`) | New. Both upstreams treated a second answer as an error. It is not: two people answering during an incident is ordinary, and the loser's surface needs the *winning answer* to tell its human what the question was actually answered with |
| `SUPERSEDED` as distinct from `EXPIRED` | New. "This timed out" invites somebody to raise it again and "this no longer applies" does not, and a run that concluded with a question open produces the second |
| The credential refusal (`secret_request_term`) | New, and it is Article IV's last hole. Neither upstream constrained what could be asked. Narrow on purpose: a question that *mentions* a credential is legitimate, and refusing the subject rather than the disclosure would teach the agent that credentials are undiscussable |
| A measured, reported propagation budget (`Propagation`) | T's closure fanned out and returned nothing measurable. Nothing is cancelled when the budget is exceeded — "the console took nine seconds and may still be showing a button" is a fact an operator can act on, where a cancelled delivery is a surface that never closed |
| Interactions travelling inside the session record | New. S persisted nothing about a pending question; T stored approvals in their own table with no link to a suspended run. One write and one read means there is no arrangement of two stores where "is this still answerable" depends on which you asked |
| Expiry decided on read, at resumption | New. A question raised before a weekend outage is not answerable when the deployment returns, and offering it would hand somebody a button that reasons about a cluster which no longer exists. It comes back `EXPIRED` rather than dropped, because "you missed this" is something the person resuming needs told |
| Progress exempted while a run is already blocked | New. Neither upstream had progress reporting at all. A run waiting on a human has already asked somebody, on a surface already showing it; telling them it is still going repeats their own unanswered question back at them |
| `share_control_with` on the loop | New, and forced by 004's own design: a specialist runs in its own loop instance, so a reap that did not share the parent's stop signal would report success and stop nothing |

### Feature 019 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| The published JSON schema per command (`surfaces/cli/output/schemas.py`) | New. T had `--json` on most commands and documented none of them, so the shape was whatever the last change left. Publishing one closed schema per command — and walking the typer application to fail on a command that has none — is what turns "machine-readable" into a contract a script can be written against |
| The exit-code contract as named constants with a printed reference (`surfaces/cli/errors.py`) | New. T returned 0 or 1. A script that has to distinguish "not configured" from "you named a run that does not exist" cannot, and the operator writing it discovers that during an incident |
| `Terminal` as a value, decided once and passed down | T detected capabilities at each call site, which is why its degradation was inconsistent between the CLI and the shell. One value means "what does this look like on a dumb terminal" is a test that constructs one rather than a terminal somebody has to find |
| The two-rendering table (`TableView`) with a labelled-block fallback below the readable floor | New. Both upstreams wrapped tables into unreadable fragments on a narrow terminal. The fallback is the rendering nobody designs for and everybody eventually needs |
| `PlatformClient` as one protocol over local and remote | T's CLI talked to its own process; S's console talked to an API. Neither had one surface that did both, so "point the CLI at the cluster" was a different program. One protocol makes it a flag, and makes a remote HTTP status map to the same exit code its local equivalent produces |
| Provider onboarding as a walked package (`wizard/providers/`) | T hard-coded three providers in the wizard body. Walking the directory is what makes the ninth provider a module rather than a ninth branch — and it is the only way the local provider is offered with the same weight as the hosted ones, which is Article VI at the surface rather than in the adapter layer |
| Integration prompts generated from the credential schema | T wrote a prompt block per vendor. Generating them is what makes a catalogue of eighty-five integrations addable one package at a time, and it is the same property capability discovery has |
| `Prompter` as a protocol with a scripted implementation | New. T's wizard could only be exercised by typing into it, so it was not exercised. The whole onboarding flow is now a unit test, including the ninth provider |
| The redacted diagnostic bundle rendered through the report sink | New. T's `doctor` printed everything and left the operator to decide what was safe to paste into a support thread. Routing it through `Sink.REPORT` is FR-023 made concrete: the terminal may show full detail, the file that exists to be shared may not |
| `surfaces/entrypoint.py` | New, and forced by this repository's own `platform/` shadowing. A console script starts with the stdlib ahead of site-packages, so an entry point that imported the application directly would find the stdlib `platform` and fail on `platform.observability`. The path is fixed before the first first-party import, which is why this is a separate module rather than a function in `app.py` |
| Interaction rendering that shows the diff, the blast radius, *and* the rollback plan, every time | T showed a summary and a link. An approval granted without seeing the rollback plan is an approval of something nobody has established is reversible, and abbreviating for a change the renderer judged small would be making the judgement the reviewer is there to make |
| Refusing anything but `approve`/`decline` | New. T accepted `y`, `yes`, and a thumbs-up reaction. An approval is the one place where reading an ambiguous answer generously applies a production change nobody agreed to |
| Compaction that keeps every evidence reference | T's `/compact` summarised the transcript and dropped what it summarised. A conclusion whose basis was dropped to save tokens is a conclusion the trace cannot support, which is the one economy a transcript may not make |

### Feature 022 — what came from where

| Source | Upstream path | Disposition | NinjaSRE destination | Notes |
|---|---|---|---|---|
| T | `gateway/slack/{events,client,output_sink,approvals,thread_history,socket_mode_worker,channel_intro,security}.py` | ADAPT | `gateway/slack/` | **Shipped in 022.** Split along the new seam: parsing in `events.py`, payload building in `client.py`, Block Kit in `interactions.py`, the port implementation in `output_sink.py`. Socket Mode and HTTP events became one `SlackIngress` with a mode, because the upstream had two code paths and they had already diverged |
| T | `gateway/telegram/` | ADAPT | `gateway/telegram/` | **Shipped in 022.** Polling/webhook selection, inline keyboards, group and direct chats. The 64-byte callback ceiling is now checked at build time rather than discovered when a button silently fails |
| T | `gateway/discord/{worker,dispatcher,components,approvals,background}.py` | ADAPT | `gateway/discord/` | **Shipped in 022.** The background worker keeps the upstream's shape and fixes the reaping: strong task references, cancellation propagated rather than swallowed, exceptions retrieved |
| T | `gateway/attachments/inline.py` | ADAPT | `gateway/chat/chunking.py` | **Shipped in 022.** The truncation idea inverted: the upstream cut a long body with an "omitted" marker, which is exactly what FR-005 forbids. Splitting on structure with a fallback chain down to the character, or attaching, both delivering everything |
| T | `gateway/runtime/live_sink.py`, `status_messages.py` | ADAPT | `gateway/chat/streaming.py` | **Shipped in 022.** In-place editing kept. The upstream's per-platform copy of "how often" became one computed interval; `user_facing_error_message` became `SinkGuard.render_failure(sink=Sink.CHAT)`, which the platform already had |
| T | `gateway/{slack,discord}/principal.py` | ADAPT | `gateway/chat/identity.py` | **Shipped in 022.** The mapping seam kept; the fallback removed. The upstream attributed an unknown workspace to the configured organisation with a warning — a permissive default this replaces with a refusal that names the role to ask for |
| S | `teams-bot/{app,bot_handlers,card_builder,stream_handler,progress_text,tool_display}.py` | ADAPT | `gateway/teams/` | **Shipped in 022.** Adaptive Cards and `updateActivity` streaming are the upstream's. The conversation reference travelling with each activity rather than being held globally is not — the upstream was single-tenant |
| S | `teams-bot/investigation_runner.py` | REFERENCE | `gateway/chat/session.py` (`ChatRuntime`) | The upstream composed a runtime inside the bot. Here it is a protocol, for the same reason `gateway/http/services.py`'s is: composing one is a deployment concern |

### Feature 022 — written fresh, not adapted

| Module | Why it has no upstream |
|---|---|
| `gateway/chat/port.py` and the four adapters behind it | Neither upstream had a chat abstraction. T wrote Slack, Telegram, and Discord three times — three streaming implementations, three approval renderers, three identity paths — and they had already drifted: the Discord one had no thread history and the Telegram one had no approvals. One port is the whole point of the feature |
| `gateway/chat/contract.py` — the contract as runtime data | New. A shared contract that lives in a document is one nobody re-reads. Ten rows a test parameterises over means a platform added to the constant without an adapter fails the build, which is the only version of SC-001 that stays true |
| Coalescing with a `dropped` counter asserted to stay zero | T's live sink dropped updates under rate-limiting and logged it. That is the thing FR-009 forbids, and the way to be sure is for nothing to have a discard path: an update replaces the pending snapshot, so the *content* always goes out |
| The edit interval computed from each platform's own budget | New. Both upstreams used one interval everywhere. Three seconds is twenty edits a minute — inside Discord's budget, past Slack's — and a two-hundred-event run is exactly where that difference bites. Found by the SC-003 test, not by review |
| `gateway/chat/routing.py` — channel to team, with an unrouted channel refused | T resolved a workspace to the single configured organisation. That is a single-tenant assumption, and here it would put one team's incident in another team's window. An unrouted channel is refused rather than defaulted, matching how an unknown node denies in `platform/identity/authorisation.py` |
| Thread history framed as attributed, quoted observation | T concatenated thread history into the prompt as prose. The framing is the mitigation that survives contact with an adversary in the channel: a block of unattributed text is the shape an instruction takes, and a transcript with names on it is the shape evidence takes |
| `gateway/chat/transport.py` — every platform call through the credential proxy | Both upstreams read bot tokens from the environment. Here there is no constructor parameter that could hold one, and a test asserts that structurally. The three refusal shapes the four platforms use — a 429, a 5xx, and a 200 carrying `ok: false` — are translated once, because every shared behaviour branches on the difference |
| `ChatSink` as an `InteractionSurface`, every instance named `chat` | New, and it is what makes SC-002 and SC-008 the same mechanism. T's Slack approvals closed cross-surface; its Discord ones did not. One name means an interaction addressed to chat reaches every configured channel without a routing list anybody has to maintain |
| Nothing raising into a run | T's Slack sink propagated a transport failure into the investigation. A chat surface that can fail a run makes the run less reliable than not having the surface — so a platform that has gone away is recorded, handed to the fallback, and left behind |
| One command catalogue rendered four ways | Both upstreams declared commands per platform. T's Slack and Discord command lists had already diverged by two commands. Generating all four from one catalogue is Article IX, and it is the only reason the fourth platform's list is correct |

## Attribution requirements checklist

- [ ] `NOTICE` names both upstream projects with copyright lines and licence reference
- [ ] `LICENSE` is Apache 2.0
- [x] ~~Every ADOPT/ADAPT file carries a provenance header~~ — **superseded by
      ADR 0011.** Attribution lives in `README.md` and `NOTICE` only. A
      provenance header in a source file would name an upstream project in a
      committed file, and a committed file must not depend on this uncommitted
      one. This map is the record instead.
- [ ] `README.md` credits both projects in a "Built on" section
- [ ] This map is updated in the same commit as any new derived code
