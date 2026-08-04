# NinjaSRE

**The AI SRE that learns — and proves it.**

NinjaSRE is a self-hosted AI SRE platform. It investigates production incidents,
produces evidence-backed root causes, remembers what it learned, and measures
continuously whether that memory is making it better.

> **Status: specification phase.** This repository currently contains the
> constitution, architecture, and feature specifications that define the MVP.
> Implementation follows the waves in [`docs/roadmap.md`](docs/roadmap.md).

---

## Why

Existing AI SRE tools split into two camps. One measures investigation quality
rigorously but starts every incident from zero. The other learns from past
incidents but cannot prove the learning helps.

NinjaSRE closes the loop:

```
INVESTIGATE → DIAGNOSE → REMEMBER → SYNTHESISE → EVALUATE
     ^                                               |
     └───────────────────────────────────────────────┘
```

Every investigation deposits an episode. Episodes become strategy playbooks.
Playbooks change the next investigation. A ground-truth scenario suite measures
whether that change was an improvement — and fails CI when it is not.

## Principles

| | |
|---|---|
| **Evidence over assertion** | Every claim names the observation behind it |
| **Bounded autonomy** | Every loop, budget, and cap is a named constant |
| **Read-only by default** | Writes require human approval and a stored rollback plan |
| **Secrets never reach the agent** | All authenticated calls go through a mandatory credential proxy |
| **Provider neutral** | Nine LLM providers at parity, including fully local models |
| **Learning is measured or not claimed** | Every memory mechanism ships with an ablation |
| **Your data stays yours** | No telemetry, no phone-home, no hosted control plane |

Ratified in [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Documentation

| Document | What it covers |
|---|---|
| [Constitution](.specify/memory/constitution.md) | The thirteen non-negotiable articles every spec must satisfy |
| [Vision](docs/vision.md) | The problem, the thesis, who it is for, what it is not |
| [Architecture](docs/architecture.md) | Package tiers, runtime, capability model, data, trust boundary, evaluation |
| [Roadmap](docs/roadmap.md) | 31 features across 8 waves, with dependencies and exit criteria |
| [Provenance map](docs/provenance-map.md) | What was taken from each upstream, how, and why |
| [ADRs](docs/adr/README.md) | The ten decisions that shape everything else |
| [Specifications](specs/) | `spec.md` / `plan.md` / `tasks.md` per feature |

## Built on

NinjaSRE is a greenfield system that deliberately reuses the strongest parts of two
Apache-2.0 predecessors:

- **[Tracer-Cloud/opensre](https://github.com/Tracer-Cloud/opensre)** — the
  investigation pipeline, the bounded ReAct runtime, the synthetic evaluation
  environment, the LLM provider abstraction, reversible masking and guardrails,
  and the CI-enforced layered architecture.
- **[swapnildahiphale/OpenSRE](https://github.com/swapnildahiphale/OpenSRE)** —
  episodic memory and strategy synthesis, the service topology graph, the skill
  methodology model with progressive disclosure, hierarchical multi-tenant
  configuration, the web console, and the credential proxy and sandbox isolation
  model.

See [`docs/provenance-map.md`](docs/provenance-map.md) for the module-level record
and [`NOTICE`](NOTICE) for attribution.

Neither upstream is affiliated with this project.

## Licence

Apache License 2.0 — see [`LICENSE`](LICENSE).
