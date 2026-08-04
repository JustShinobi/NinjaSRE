# core/ — agent runtime, pipeline, domain rules

**Tier 3.** May import: `config`, `platform`. Must never import: `capabilities`, `integrations`, `gateway`, `surfaces`.

The canonical ReAct loop and its guardrails, the six investigation stages, the
state and evidence model, the LLM provider abstraction, the capability framework
primitives, and pure domain rules.

## Conventions

- The first-party ReAct loop is the *only* runtime used for evaluation and
  benchmarks. Alternative adapters sit behind `agent/runtime_port.py`, are marked
  experimental, and never produce a published number (Article V).
- A pipeline stage is a pure `(state) -> updates` function. Its exception is
  recorded and re-raised — never swallowed.
- Every bound the loop enforces is a named constant in
  `config/constants/investigation.py` (Article II).
- No vendor LLM SDK outside `llm/` (Article VI).

## Where things go

- Runtime mechanics → `agent/`. Stage logic → `pipeline/`. State shape → `state/`.
- Provider adapters → `llm/providers/`. Schema normalisation → `llm/`.
- A rule with no I/O and no dependency → `domain/`. That package is the one that
  stays testable without a single mock.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `core/`.
