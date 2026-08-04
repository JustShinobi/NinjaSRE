# ADR 0008 — Full parity across all supported LLM providers

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article VI, Article XII

## Context

The pipeline design supports nine LLM providers with varying depth. The memory design targets Anthropic
directly, with other providers reachable only through an optional LiteLLM proxy —
a path that is notably fragile for tool calling and structured output, where
provider differences are sharpest.

Provider differences that actually break agents:

| Difference | Consequence |
|---|---|
| Tool-schema dialect (draft-07 constructs, `type: ["object","null"]`, nested `anyOf`) | Passes local validation, rejected by the provider API on first invoke — and because all selected tools are sent together, one bad schema fails the whole turn |
| Structured output mechanism (native JSON mode vs tool-call coercion vs prose parsing) | The `diagnose` stage silently degrades to regex fallback |
| Streaming event shapes | Progress events differ or disappear per surface |
| Parallel tool calls | Supported, serialised, or rejected |
| Token accounting fields | Cost tracking wrong or absent |
| Prompt caching semantics | Cache markers rejected, or a 400 that must be retried uncached |
| Reasoning-effort controls | Only some providers expose them |

## Decision

**All supported providers reach full parity in v1, verified by one shared contract
test suite.**

Supported providers:

| Provider | Notes |
|---|---|
| Anthropic | Reference implementation; prompt caching, reasoning effort |
| OpenAI | Chat Completions and Responses transports |
| Azure OpenAI | Deployment-name addressing, separate auth |
| AWS Bedrock | Converse API, model-id mapping |
| Google Gemini | Native tool calling |
| Google Vertex AI | Service-account auth |
| OpenRouter | OpenAI-compatible aggregator |
| NVIDIA NIM | OpenAI-compatible, self-hostable |
| Ollama / vLLM | Local models — **required** for a no-egress deployment |

Parity means the same contract suite passes for each: tool calling, tool-schema
normalisation, structured output, streaming, retry and backoff, failure
classification, token and cost accounting, and prompt caching where supported.

Where a provider genuinely lacks a capability, the abstraction **degrades
explicitly and reports the degradation** — it never silently produces a different
behaviour.

## Rationale

**Article VI is not satisfiable partially.** "Provider neutral" with one properly
tested provider and eight best-effort ones is single-provider software with extra
configuration. Self-hosted operators who cannot send data to a US API endpoint need
Ollama or vLLM to be genuinely first-class, not nominally supported.

**Provider bugs are silent and expensive.** Schema-dialect failures do not degrade
gracefully; they fail the turn. The only way to know a provider works is to run
the contract suite against it.

**The abstraction already exists in prior art.** The pipeline design's provider layer, transports,
and `tool_schema_normalize` module are directly adoptable. The incremental cost is
mainly test coverage, not new architecture.

**Proxy-only multi-provider is a false economy.** LiteLLM is a fine convenience
layer, but placing it on the critical path for tool calling means debugging
someone else's translation of someone else's dialect. It remains available as an
option, not as the mechanism.

## Cost management

Full parity multiplies CI cost if every scenario runs on every provider. The
tiering below keeps this bounded:

| Tier | Providers | CI cadence |
|---|---|---|
| **Contract** | All 9 | Every PR — schema, streaming, structured output, retry, accounting. Uses recorded fixtures; no live tokens |
| **Smoke** | Anthropic, OpenAI, Ollama | Every PR — a small live scenario subset |
| **Full suite** | Anthropic (reference) | Every PR — the complete scenario corpus and regression gate |
| **Cross-model** | All 9 | Nightly and pre-release — the full corpus, producing the comparison benchmark |

The published benchmark number is always from the canonical runtime
(ADR 0003) on the reference provider, with the cross-model table alongside it.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Anthropic only in v1, multi-provider in v2 | Violates Article VI and eliminates the self-hosted-with-local-models use case that motivates the product |
| Tier-1 providers fully tested, tier-2 best-effort | The untested tier's failures land on users during incidents, which is the worst possible time |
| LiteLLM proxy as the only multi-provider path | Puts a third-party translation layer on the critical path for the most fragile part of the stack |

## Consequences

**Positive**

- Any supported provider can be chosen without risk
- Fully local, zero-egress deployment is real
- The cross-model benchmark becomes a genuine product artefact
- Provider-specific bugs surface in CI, not in an incident

**Negative**

- Nine adapters to maintain against independently-changing vendor APIs
- Contract fixtures need periodic refresh as APIs evolve
- Nightly cross-model runs consume real tokens

**Mitigations**

- Recorded-fixture contract tests keep per-PR cost near zero
- A single shared normalisation layer means most dialect fixes are one change
- Adding a provider is a scaffold plus a contract-suite run, not bespoke work
- Nightly runs are scoped to a representative scenario subset with a full run only
  before a release
