# ADR 0001 — Greenfield repository with deliberate module reuse

- **Status:** Accepted
- **Date:** 2026-08-04
- **Deciders:** Project owner
- **Constitution impact:** Articles VIII, XIII

## Context

Two existing Apache-2.0 systems solve different halves of the same problem, and
NinjaSRE wants both halves. Throughout these ADRs they are referred to by what
they are good at rather than by name:

- **The pipeline design** — a large production Python codebase. Layered
  architecture with CI-enforced import boundaries, a deterministic six-stage
  investigation pipeline, a bounded ReAct loop, a broad vendor integration
  catalogue, a nine-provider LLM abstraction, reversible masking, a guardrail
  engine, and a synthetic-scenario evaluation environment with ground-truth
  answer keys.
- **The memory design** — a smaller Python and TypeScript codebase. Episodic
  memory in a graph store, LLM-synthesised strategy playbooks, a service topology
  graph, a large catalogue of methodology-rich skills, hierarchical multi-tenant
  configuration, a Next.js console, and a credential proxy with per-thread
  sandbox isolation.

Four options were considered:

1. Fork the pipeline design, port memory and platform features into it
2. Fork the memory design, port pipeline and evaluation into it
3. Greenfield repository reusing modules from both
4. Monorepo tracking both as vendored dependencies

## Decision

**Greenfield repository with deliberate module reuse.**

A new repository with its own architecture, into which prior modules are brought
at four levels of fidelity — adopt, adapt, rewrite, reference — decided per
module.

## Rationale

**Against forking the pipeline design (option 1).** Its architecture is the
better starting point, but the changes required are structural, not additive: a
persistence layer must be introduced where none exists, the capability model must
absorb skills, the credential proxy must become mandatory (touching every
integration client), and multi-tenancy must be threaded through state that was
designed single-tenant. That is not porting features into a fork — it is
rewriting the fork's foundations while carrying its history and its hosted-SaaS
concerns (billing, identity vendor, telemetry) as dead weight.

**Against forking the memory design (option 2).** It ships product value faster,
but comes with a 75KB agent module, a 76KB sandbox manager, two divergent server
implementations, a hard dependency on a single vendor's agent SDK, and no
enforced architectural boundaries. Fixing those is a rewrite performed under the
constraint of not breaking a working system — the slowest possible path.

**Against the monorepo (option 4).** Both move independently and neither is
designed as a library. Continuous merge conflict for a compatibility benefit
nobody will use once NinjaSRE's contracts diverge — which they must, given the
constitution.

**For greenfield.** The architecture must satisfy constraints neither system was
built for: mandatory credential proxy, single datastore, provider neutrality with
local-model viability, measured learning with ablation, and CI-enforced layering.
Those constraints are foundational, not incremental. Starting from them and
bringing in proven implementations is cheaper than retrofitting them into either
existing shape.

Critically, greenfield here does **not** mean rewriting from scratch. The plan
targets substantial direct reuse of the highest-value assets: domain rules,
masking, guardrails, context budget, provider layer, scenario corpus, and mock
backends from the pipeline design; memory models, strategy synthesis, config
hierarchy, skill methodology content, and the SSE event protocol from the memory
design.

## Consequences

**Positive**

- Architecture is designed against the constitution rather than negotiated with it
- No inherited hosted-SaaS coupling, telemetry, or dual implementations
- Free choice of module granularity per subsystem

**Negative**

- No inherited git history; bug-fix backports must be applied manually
- Higher upfront cost before the first working investigation
- Risk of re-introducing bugs the prior systems already fixed

**Mitigations**

- Footgun documentation from the pipeline design's contributor guide is adapted
  rather than discarded
- Its synthetic scenario corpus is adopted early, so regressions relative to
  known-good behaviour surface immediately

## Compliance

- `README.md` and `NOTICE` carry the attribution both licences require
  (see [ADR 0011](0011-attribution-in-readme-only.md))
