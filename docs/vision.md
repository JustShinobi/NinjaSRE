# NinjaSRE — Vision

## The problem

When production breaks, the evidence is scattered: logs in one system, metrics in
another, traces in a third, the deploy history in a fourth, and the one person who
remembers the last time this happened is asleep.

AI SRE tools have attacked this from two directions, and both stop short.

**The measurement school** builds a rigorous investigation engine: deterministic
pipelines, bounded reasoning loops, synthetic incident scenarios with ground-truth
answer keys, trajectory scoring. It can tell you, precisely, whether the agent got
the right answer for the right reasons. But it starts every incident from zero. It
has no memory of the outage it solved last Tuesday.

**The memory school** builds a learning platform: episodic memory of past
investigations, service topology graphs, synthesised playbooks. It gets smarter
about *your* infrastructure over time. But it cannot prove it. There is no ground
truth, no trajectory scoring, no regression gate — so "it learns" remains an
assertion.

Neither closes the loop. Measuring without remembering means never compounding.
Remembering without measuring means never knowing whether the memory helps or
merely adds confident noise.

## The thesis

> **An AI SRE that learns must be able to prove it learned.**

NinjaSRE is built around a single closed loop:

```
      ┌──────────────────────────────────────────────────────┐
      │                                                      │
      v                                                      │
  INVESTIGATE ──> DIAGNOSE ──> REMEMBER ──> SYNTHESISE ──> EVALUATE
  bounded ReAct   evidence-    episodic     strategy       ground-truth
  loop over       backed       memory       playbooks      scenarios,
  typed           structured   with         with           trajectory
  capabilities    root cause   effective-   anti-          scoring,
                               ness score   patterns       CI gates
```

Every investigation deposits an episode. Episodes accumulate into strategies.
Strategies change how the next investigation is conducted. And the scenario suite
measures whether that change was an improvement — in accuracy, in trajectory
efficiency, and in resistance to red herrings.

When the loop is closed, three things become possible that are impossible with
either half alone:

1. **Ablation.** Run the suite with memory off and memory on. The delta is the
   value of memory, in a number.
2. **Regression detection.** A prompt change, a model upgrade, or a new
   integration that degrades diagnosis quality fails CI before it ships.
3. **Honest improvement claims.** "v1.3 resolves 71% of tier-3 scenarios versus
   64% in v1.2" is a statement that can be checked.

## Who it is for

Platform and SRE teams who:

- run their own infrastructure and cannot send production telemetry to a
  third-party SaaS
- are on-call for systems complex enough that tribal knowledge is a real asset
- want investigation automation but not autonomous remediation by default
- need to justify the tool internally with evidence, not vendor claims

## What it is not

- **Not a monitoring system.** It consumes your observability stack; it does not
  replace it.
- **Not an autonomous remediator.** Production changes require a human decision.
  Autonomy is opt-in, allow-listed, and revocable.
- **Not a SaaS.** There is no hosted control plane, no phone-home, no telemetry.
- **Not model-locked.** Any supported provider, including fully local models.

## Design commitments

These are the commitments that shape every technical decision. They are ratified
in `.specify/memory/constitution.md`.

| Commitment | What it rules out |
|---|---|
| Every claim names its evidence | Plausible-sounding root causes with nothing behind them |
| Every loop is bounded by a named constant | Runaway agents and unpredictable cost |
| Read-only by default, approval + rollback for writes | An agent that scales a deployment to zero at 3am |
| Secrets never enter the agent's reach | Credential leakage into prompts, logs, or third-party models |
| One canonical runtime | Benchmark numbers that mean different things |
| Provider-neutral, local models viable | A "self-hosted" tool that mandates a US API endpoint |
| Learning is measured or not claimed | Memory as decoration |
| One database | A self-hosted stack with four backup strategies |

## The shape of the product

A single self-hosted deployment provides:

- a **web console** for investigations, memory, configuration, and approvals
- a **CLI and REPL** for local work and operations
- a **REST API with SSE** and webhook ingestion for alert-triggered investigation
- **chat surfaces**: Slack, Microsoft Teams, Telegram, Discord
- **push notifications** via Pushover and other sinks
- **~85 integrations** across observability, cloud, databases, data platforms,
  version control, incident management, and communication
- **multi-tenancy** with hierarchical org → team configuration, RBAC, SSO, and a
  full audit trail
- an **evaluation suite** — synthetic scenarios, chaos experiments, and cloud e2e
  — that runs in the operator's own CI

## Prior art

NinjaSRE is a greenfield system that deliberately reuses the strongest parts of
two Apache-2.0 predecessors, referred to throughout the ADRs by what each is good
at:

- **The pipeline design** — the investigation engine, the bounded runtime, the
  evaluation environment, the provider abstraction, masking and guardrails, and
  the layered architecture with CI-enforced boundaries.
- **The memory design** — episodic memory and strategy synthesis, the knowledge
  graph, the skill model with progressive disclosure, hierarchical multi-tenant
  configuration, the web console, and the credential proxy and sandbox isolation
  model.

[ADR 0001](adr/0001-greenfield-with-module-reuse.md) records why a greenfield
repository was chosen over forking either. Attribution lives in `README.md` and
`NOTICE` — and, per [ADR 0011](adr/0011-attribution-in-readme-only.md), nowhere
else.
