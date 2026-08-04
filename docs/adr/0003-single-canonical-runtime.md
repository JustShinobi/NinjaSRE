# ADR 0003 — One canonical runtime, SDK adapter experimental only

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article V, Article II, Article VI

## Context

The prior systems differ fundamentally in who drives the agent loop.

**The pipeline design** implements its own ReAct loop. Guardrails live inside it: a per-turn
schema cap, an iteration ceiling, a duplicate-call cache that tells the model it
already has a result, a stagnation breaker that strips tool access after N sterile
iterations, a context budget with evidence eviction, and deterministic seed calls
that execute before the model's first turn.

**The memory design** uses the Claude Agent SDK. The SDK session *is* the runtime. It
provides specialist sub-agents via the `Task` tool, skills with progressive
disclosure, background task execution, and lifecycle hooks — substantial
capabilities for very little code.

The question raised during design was direct: *why not have both?*

## Decision

**One canonical runtime — the first-party ReAct loop — which absorbs the
capabilities the SDK provides.** A `ClaudeAgentSdkRuntime` adapter may implement
the runtime port, but it is experimental, never the default, and never produces a
published benchmark number.

## Rationale

Capabilities and runtimes are different things, and only capabilities compose.

**Two runtimes break evaluation.** The product's differentiator is measuring
trajectory quality against golden trajectories and failing CI on regression. That
comparison is only valid if every scenario runs the same way. Split the suite
across two runtimes and every number becomes ambiguous — a score change could be
the model, the prompt, the memory, or the runtime, and no one can tell which.

**Guardrails are not portable.** The stagnation breaker, duplicate cache, schema
cap, and context budget are properties of loop control flow. In the SDK the loop
belongs to the vendor; there is no seam to insert them. An SDK-backed run would
silently run without Article II's bounds.

**Vendor neutrality is a stated requirement.** Article VI requires local models to
be fully viable. A runtime that only exists for one vendor's models cannot be the
canonical one in a self-hosted product.

**The SDK's value is its capabilities, and those are implementable.** Each is a
bounded piece of work in the first-party loop:

| SDK capability | First-party implementation |
|---|---|
| Specialist sub-agents (`Task`) | Sub-loops with isolated context, capability subset, and budget; return a structured finding, not a transcript |
| Skills with progressive disclosure | Registry with cheap metadata and on-demand body loading (ADR 0002) |
| Background/parallel task execution | Executor keyed on the `parallel_safe` metadata tools already declare |
| Mid-run message queue | Debounced merge at turn boundaries |
| Lifecycle hooks | Explicit `PreToolUse`/`PostToolUse`/`OnTurnEnd` hook points — where memory finalisation and guardrails attach |
| `AskUserQuestion` | Human-handoff capability with surface-specific rendering |
| Todo/progress tracking | Progress events on the SSE stream |

Estimated additional cost: ~3–5k LOC in `core/agent/`. In exchange: nine
providers, enforceable guardrails, and trustworthy measurement.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Adopt the SDK as the runtime | Forfeits provider neutrality and all in-loop guardrails; makes trajectory evaluation vendor-dependent |
| Two first-class runtimes with guardrail parity | Doubles the test surface and requires reimplementing every guardrail inside a loop we do not control — the work of building our own loop, plus a dependency |
| No adapter at all | Loses a cheap compatibility path for users already invested in the SDK, at no cost given the port already exists |

## Consequences

**Positive**

- Every benchmark number is comparable
- Guardrails apply universally
- Local models fully supported
- Runtime behaviour is fully observable and modifiable

**Negative**

- More runtime code to own and maintain
- Sub-agent orchestration, parallelism, and hooks must be built rather than
  inherited
- The experimental adapter is a support-question surface

**Mitigations**

- The runtime port is defined in Wave 0 so the adapter never becomes load-bearing
- The adapter's documentation states explicitly which guardrails it does not
  enforce
- CI runs the evaluation suite only on the canonical runtime; a guard test fails
  if a benchmark is invoked with a non-canonical runtime
