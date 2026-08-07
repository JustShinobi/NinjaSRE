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

The operator-facing documentation is a site under [`docs/site/`](docs/site/index.md),
buildable and servable with no network at all:

```bash
make docs-build   # renders it into docs/site/build
make docs-serve   # builds it and serves it on localhost
```

Start at the [quickstart](docs/site/quickstart/index.md) — it takes a new
operator from nothing to a finished investigation without needing any other
page. The capability, integration, and configuration references are **generated**
from the same declarations the runtime reads, and `make verify` fails if they
were not regenerated after a change.

| Document | What it covers |
|---|---|
| [Quickstart](docs/site/quickstart/index.md) | Nothing to a finished investigation, self-contained |
| [Deployment](docs/site/deployment/index.md) | The three profiles, upgrading, backups, keys, air-gapped operation |
| [Security model](docs/site/security/index.md) | The five controls, each with the threat it addresses |
| [Evaluation](docs/site/evaluation/index.md) | The exact commands to reproduce every published number |
| [Constitution](.specify/memory/constitution.md) | The thirteen non-negotiable articles every spec must satisfy |
| [Vision](docs/vision.md) | The problem, the thesis, who it is for, what it is not |
| [Architecture](docs/architecture.md) | Package tiers, runtime, capability model, data, trust boundary, evaluation |
| [Roadmap](docs/roadmap.md) | 31 features across 8 waves, with dependencies and exit criteria |
| [ADRs](docs/adr/README.md) | The eleven decisions that shape everything else |
| [Contributing](AGENTS.md) | Tier table, file placement, code style, footguns, and the one command CI runs |

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

This section and [`NOTICE`](NOTICE) are where that attribution lives, and the
only place it appears — see
[ADR 0011](docs/adr/0011-attribution-in-readme-only.md).

Neither project is affiliated with this one.

## Licence

Apache License 2.0 — see [`LICENSE`](LICENSE).
