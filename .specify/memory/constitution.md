# NinjaSRE Constitution

**Version:** 2.0.0
**Ratified:** 2026-08-04
**Last amended:** 2026-08-04 — Article XIII, see [ADR 0011](../../docs/adr/0011-attribution-in-readme-only.md)
**Status:** Active

This document defines the non-negotiable principles of NinjaSRE. Every `spec.md`,
`plan.md`, and `tasks.md` in `specs/` MUST pass a Constitution Check against these
articles. A plan that violates an article is rejected unless the violation is
recorded in that plan's Complexity Tracking section with an explicit justification
and an approved amendment to this document.

---

## Preamble: What NinjaSRE Is

NinjaSRE is a self-hosted AI SRE platform for teams. It investigates production
incidents, produces evidence-backed root causes, learns from every investigation,
and proves — continuously and automatically — that it is getting better rather
than worse.

It exists because no current system closes that loop. Systems that measure
investigation quality do not remember what they learned. Systems that remember
cannot prove they improved. NinjaSRE does both, and treats the connection between
them as the product.

---

## Article I — Evidence Over Assertion

Every conclusion the system produces MUST be traceable to the observation that
supports it.

1. A root cause statement MUST carry the evidence entries that justify it. An
   unbacked claim MUST be labelled a hypothesis, never a finding.
2. Every tool invocation MUST record its inputs, outputs, duration, and outcome
   into the run trace. A tool result that never entered the trace did not happen.
3. Reports MUST separate `validated_claims` from `non_validated_claims`. The
   distinction is structural, not stylistic.
4. When the system cannot determine something, it MUST say so. Confident prose
   over thin evidence is a defect, not a UX preference.

**Rationale:** An SRE acting on a fabricated root cause at 3am is worse off than
one acting on no root cause at all.

---

## Article II — Bounded Autonomy

The agent runs inside limits that are declared in code, enforced at runtime, and
observable in the trace.

1. Every loop MUST have a hard iteration ceiling.
2. Every context window MUST have a budget with a deterministic eviction policy.
3. Every tool-schema payload MUST have a cap independent of how many capabilities
   are registered.
4. Repeated identical tool calls MUST be served from cache, and the model MUST be
   told it already has that result.
5. A loop that produces no new evidence for N consecutive iterations MUST be
   forced to conclude rather than allowed to spin.
6. Every guardrail MUST be a named constant in a single owning module, never a
   magic number at a call site.

**Rationale:** Unbounded agents fail expensively and unpredictably. Bounds that
live in configuration can be raised deliberately; bounds that live in nobody's
head cannot.

---

## Article III — Read-Only by Default

Production is not modified without a human deciding so.

1. Every capability MUST declare a `side_effect_level`. Absence of a declaration
   is treated as write, not read.
2. Any capability above read level MUST require explicit human approval before
   execution, presented at the surface the human is already using.
3. An approved action MUST record a rollback plan before it executes. An action
   with no rollback path MUST be rejected unless the operator explicitly waives
   this, and the waiver MUST be recorded in the audit log.
4. Approval is per-action and per-session. It never generalises to a later action.
5. Autonomous execution allow-lists MAY exist, but MUST be opt-in per action type,
   revocable instantly by a kill switch, and fully audited.

**Rationale:** The cost asymmetry is extreme. A missed investigation costs
minutes; an unapproved `scale --replicas=0` costs an outage.

---

## Article IV — Secrets Never Reach the Agent

The agent reasons about systems it cannot authenticate to on its own.

1. Credentials MUST NOT be present in the agent's process environment, prompt,
   tool arguments, filesystem, or trace.
2. All authenticated external calls MUST route through the credential proxy,
   which injects secrets at the network boundary based on tenant and team context.
3. Non-secret configuration (region, site, endpoint) MAY be visible to the agent.
   Anything that grants access MUST NOT be.
4. Trace, transcript, and report writers MUST pass through the guardrail engine
   before any value is persisted or transmitted.
5. Identifier masking MUST be applied before any external LLM call and reversed
   only on output rendered to an authorised human.

**Rationale:** An agent that can read a secret can leak it — into a prompt, a
log, a report, or a third-party model provider. Removing the secret from its
reach removes the entire class of failure.

---

## Article V — One Canonical Runtime

There is exactly one runtime whose behaviour defines correctness.

1. The canonical runtime is the first-party ReAct loop. It is the only runtime
   used for evaluation, benchmarking, and CI regression gates.
2. Alternative runtime adapters (e.g. Claude Agent SDK) MAY exist behind the
   runtime port, but MUST be marked experimental, MUST NOT be the default, and
   MUST NOT be used to produce any published benchmark number.
3. Guardrails from Article II are properties of the canonical runtime. An adapter
   that cannot enforce them MUST declare which ones it drops in its own docs.
4. Capabilities, memory, guardrails, masking, and persistence MUST NOT depend on
   which runtime is active.

**Rationale:** Trajectory evaluation is only meaningful if all scenarios run the
same way. Two first-class runtimes make every benchmark number ambiguous.

---

## Article VI — Provider Neutrality

No LLM vendor is load-bearing.

1. Model access MUST go through the provider abstraction. No first-party module
   outside `core/llm/` may import a vendor SDK.
2. All supported providers MUST pass the same contract test suite: tool calling,
   structured output, streaming, retry, token accounting, and schema
   normalisation.
3. A capability MUST NOT be gated on a specific provider's features. Where a
   provider lacks a capability, the abstraction MUST degrade explicitly and
   report the degradation.
4. Locally-hosted models MUST remain viable. A deployment where no data leaves
   the operator's infrastructure MUST be fully functional.

**Rationale:** Self-hosted SRE tooling that mandates a single US-based API
endpoint is not self-hosted in the sense that matters to the buyer.

---

## Article VII — Learning Is Measured or It Is Not Claimed

Memory that cannot be shown to improve outcomes is decoration.

1. Every learning mechanism (episodic memory, strategy synthesis, knowledge
   graph) MUST have a paired evaluation that measures its contribution.
2. The evaluation harness MUST support ablation: running the same scenarios with
   the mechanism disabled, so its effect is isolated.
3. Recall MUST be agent-driven, not pre-injected. Memory is retrieved after
   concrete evidence exists, never speculatively on a vague alert.
4. Stored episodes MUST record whether a root cause was identified. This flag
   means "a cause was established with evidence", never "production was fixed".
5. Regression in scenario scores MUST fail CI. Improvement claims MUST cite a
   benchmark run.

**Rationale:** "It learns" is the easiest unfalsifiable claim in this category of
product. NinjaSRE only makes it where a number backs it.

---

## Article VIII — Layered Architecture, Enforced

Dependencies point downward, and CI proves it.

1. The package tiers are:
   - **Tier 1** — `surfaces/`, `gateway/` (entry points; may import everything below; must not import each other)
   - **Tier 2** — `capabilities/`, `integrations/` (`integrations` must never import `capabilities`)
   - **Tier 3** — `core/`, `platform/` (siblings; may cross-import)
   - **Tier 4** — `config/` (leaf; imports no first-party package)
2. Import boundaries MUST be enforced by `import-linter` in CI. A rule that is
   documented but not enforced does not exist.
3. Behaviour belongs in the owning module, never in the nearest shared file that
   already imports something similar.
4. Compatibility-only forwarding modules MUST be deleted in the same change that
   migrates their callers.

**Rationale:** Both systems this one learns from converged on layering. Only one
enforced it, and only that one stayed navigable at 200k lines.

---

## Article IX — Capabilities Are Declared, Not Improvised

The agent's abilities are a typed, discoverable catalogue.

1. Every capability MUST carry declarative metadata: name, description, input
   schema, evidence source, `side_effect_level`, `parallel_safe`, approval
   requirements, use cases, and anti-examples.
2. Skills provide methodology and progressive disclosure; tools provide typed,
   schema-validated execution. A skill MUST reference the tools it directs, and
   MUST NOT be a wrapper for arbitrary shell execution against production.
3. Capability selection MUST be scored and bounded, never "send everything".
4. Adding a capability MUST NOT require editing a central registry file;
   discovery is automatic from the owning package.

**Rationale:** Free-form shell access is cheap to write and impossible to plan
against, score, or evaluate. Typed capabilities are the precondition for
trajectory measurement.

---

## Article X — The Operator Owns Their Data

Self-hosted means nothing leaves without an explicit decision.

1. NinjaSRE MUST NOT contain any first-party telemetry, analytics, crash
   reporting, or usage-tracking that transmits off-host.
2. Observability MUST be OpenTelemetry pointed at an operator-configured
   collector, disabled by default.
3. No component may phone home for version checks, licensing, or feature flags.
4. Transcripts, traces, episodes, and reports are stored in the operator's
   database and never mirrored elsewhere.

**Rationale:** The target buyer runs regulated infrastructure. Opt-out telemetry
is a procurement blocker, not a growth lever.

---

## Article XI — Single Datastore

One database holds relational config, vector memory, and the topology graph.

1. PostgreSQL with `pgvector` and Apache AGE is the canonical store.
2. Storage access MUST go through repository ports (`EpisodeStore`,
   `TopologyGraph`, `VectorIndex`, `ConfigRepository`, `RunTraceStore`). No module
   outside the persistence layer may issue SQL or Cypher directly.
3. Schema changes MUST ship as reversible migrations.
4. Alternative store adapters MAY exist behind the ports, but the reference
   deployment is a single Postgres instance.

**Rationale:** Every additional stateful service in a self-hosted stack is a
backup strategy, an upgrade path, and an on-call rotation the operator did not
ask for.

---

## Article XII — Test-First, Trace-Backed

1. Behaviour changes MUST land with tests written before the implementation.
2. Behaviour-preserving refactors MUST be guarded by a characterisation test that
   passes on the pre-refactor code and stays green through the change.
3. Every investigation-affecting change MUST report its effect on the synthetic
   scenario suite. "No effect" is an acceptable result; "not measured" is not.
4. Contract tests MUST cover every provider adapter, every integration client,
   and every capability schema.

---

## Article XIII — Language and Attribution

1. All source, comments, identifiers, commit messages, documentation, prompts,
   and user-facing text are in **English**.
2. Attribution for the Apache-2.0 work NinjaSRE draws on lives in `README.md`
   and `NOTICE`, and MUST be complete there.
3. It MUST NOT be repeated anywhere else in the repository. No per-file
   provenance headers, no provenance map, no "derived from" comments, no asides
   naming a prior project. A file that needs a fact from prior art states the
   fact.
4. A committed file MUST NOT depend on an uncommitted one — no link, no import,
   no test that reads it. Where a committed artefact needs a rule written down
   elsewhere, the rule is restated in a committed file, and that copy is the
   source of truth.

**Rationale:** Apache 2.0 obliges attribution, and one complete, maintained
statement of it discharges that obligation better than a hundred scattered
comments that drift out of date. Clause 4 exists because a check that reads a
file absent from a clean checkout does not fail — it skips, which is worse than
not existing.

---

## Governance

- **Amendment:** Changing an article requires an ADR in `docs/adr/` stating the
  driver, the alternatives, and the consequences, plus a version bump here.
- **Versioning:** MAJOR for removing or reversing an article, MINOR for adding
  one or materially expanding a clause, PATCH for wording.
- **Constitution Check:** Every `plan.md` includes a Constitution Check section
  listing each article and how the plan satisfies it. Unresolved violations block
  the plan.
- **Precedence:** This document outranks any other guidance in the repository,
  including agent instructions and tooling defaults.

---

## Article Index (quick reference for Constitution Checks)

| # | Article | One-line test |
|---|---------|---------------|
| I | Evidence Over Assertion | Can every claim name its evidence? |
| II | Bounded Autonomy | Are all loops, budgets, and caps named constants? |
| III | Read-Only by Default | Does every write require approval and a rollback plan? |
| IV | Secrets Never Reach the Agent | Could the agent read a credential anywhere in this design? |
| V | One Canonical Runtime | Does evaluation run on exactly one runtime? |
| VI | Provider Neutrality | Does this work on a local model with no cloud access? |
| VII | Learning Is Measured | Is there an ablation that isolates this mechanism's effect? |
| VIII | Layered Architecture | Does `import-linter` pass, and is the code in its owning module? |
| IX | Capabilities Are Declared | Does every capability carry full metadata and a bounded schema? |
| X | Operator Owns Their Data | Does anything leave the host without an explicit opt-in? |
| XI | Single Datastore | Does this reach storage only through a repository port? |
| XII | Test-First, Trace-Backed | Were the tests written first, and is the scenario-suite delta reported? |
| XIII | Language and Attribution | Is it in English, and does every reference in it resolve inside the repository? |
