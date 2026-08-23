# Feature 002 — LLM Provider Layer

- **Wave:** 0 — Foundation
- **Branch:** `feat/002-llm-provider-layer`
- **Status:** Draft
- **Depends on:** 001
- **Blocks:** 003, 004, 005, 010, 011, 028
- **ADRs:** [0008](../../docs/adr/0008-full-provider-parity.md)

## Summary

A provider-agnostic LLM abstraction supporting nine providers at full parity:
tool calling, structured output, streaming, retry, failure classification, token
and cost accounting, prompt caching, and — critically — tool-schema normalisation
that prevents provider-specific schema dialects from failing a turn.

## User scenarios

### Primary story

An operator with no permitted egress to third-party APIs configures a local Ollama
model and runs investigations with the same capabilities, guardrails, and report
quality as an operator using Anthropic.

### Acceptance scenarios

1. **Given** any supported provider configured, **when** an investigation runs,
   **then** tool calling, structured output, and streaming all function, and token
   usage is recorded.
2. **Given** a tool whose JSON Schema uses a draft-07 construct
   (`"type": ["object", "null"]`), **when** the schema is sent to a provider that
   rejects it, **then** the normalisation layer rewrites it to an accepted form
   and the call succeeds.
3. **Given** a provider that does not support parallel tool calls, **when** the
   loop requests parallel execution, **then** the adapter serialises the calls and
   reports the degradation in the run trace.
4. **Given** a transient provider error (429, 5xx, timeout), **when** it occurs,
   **then** the request is retried with exponential backoff up to the configured
   ceiling, and each attempt is recorded.
5. **Given** a non-transient provider error (401, 400 schema rejection), **when**
   it occurs, **then** it is classified, not retried, and surfaced with an
   actionable message that contains no exception internals at external surfaces.
6. **Given** two concurrent turns sharing a cached client instance, **when** one
   turn's error handler mutates client state, **then** the other turn's behaviour
   is decided by what its own request carried, not by the mutated flag.
7. **Given** a provider that supports prompt caching, **when** cache markers are
   rejected with a 400, **then** the request is retried once without markers and
   the turn completes.
8. **Given** a structured-output request, **when** the provider lacks native JSON
   mode, **then** the adapter falls back to tool-call coercion, and only then to
   parsing, recording which mechanism was used.

### Edge cases

- A provider returning a tool call for a tool not in the sent schema set.
- Token accounting when the provider omits usage fields on streamed responses.
- A model whose context window is smaller than the configured budget.
- Bedrock model-id and region mapping when the configured id is an inference profile.
- Azure OpenAI deployment-name addressing differing from the model name.
- Vertex AI service-account credentials expiring mid-run.
- Ollama returning a partial JSON tool call from a quantised model.

## Requirements

### Functional

- **FR-001** The layer MUST support: Anthropic, OpenAI, Azure OpenAI, AWS Bedrock,
  Google Gemini, Google Vertex AI, OpenRouter, NVIDIA NIM, and Ollama/vLLM.
- **FR-002** No first-party module outside `core/llm/` may import a vendor SDK. A
  CI check MUST enforce this.
- **FR-003** A single `LLMClient` protocol MUST expose: `invoke`, `stream`,
  `invoke_structured`, and `count_tokens`. All providers implement it.
- **FR-004** Tool schemas MUST be normalised per provider before transmission,
  covering at minimum: union types, nullable types, nested `anyOf`/`oneOf`,
  `additionalProperties`, unsupported `format` values, and required-field
  placement.
- **FR-005** Normalisation MUST be validated by a contract test that sends **every
  registered capability schema together** — the failure mode is combinatorial, not
  per-schema.
- **FR-006** Structured output MUST use, in order of preference: native structured
  output, tool-call coercion, then prose parsing. The mechanism used MUST be
  recorded.
- **FR-007** Retry MUST use exponential backoff with jitter, a configurable
  attempt ceiling, and MUST NOT retry non-transient classifications.
- **FR-008** Failures MUST be classified into a closed taxonomy: `transient`,
  `rate_limited`, `auth`, `schema_rejected`, `context_exceeded`,
  `content_filtered`, `model_unavailable`, `unknown`.
- **FR-009** A provider failure MUST degrade the caller to a partial result
  preserving prior work; it MUST NOT propagate as an unhandled exception.
- **FR-010** Token usage (input, output, cached, reasoning where available) and
  computed cost MUST be recorded per call, per turn, and per run.
- **FR-011** Client instances MAY be cached per role. Any state a request depends
  on MUST be captured locally when the request is built, never read from mutable
  client state in an error handler.
- **FR-012** Prompt caching MUST be supported where the provider supports it, with
  a single uncached retry when cache markers are rejected.
- **FR-013** Reasoning-effort controls MUST be exposed where supported and ignored
  with a recorded note where not.
- **FR-014** Two transports MUST be supported: direct vendor SDK (default) and
  LiteLLM (optional). Transport choice MUST NOT change observable behaviour.
- **FR-015** Provider credentials MUST be resolved through the credential vault
  (feature 007) once available; until then, through an injectable resolver — never
  read directly from the environment at the call site.
- **FR-016** Model metadata (context window, max output, tool-calling support,
  structured-output support, parallel-call support, pricing) MUST live in a
  provider registry and be queryable before a call is made.
- **FR-017** Exception detail MUST NOT reach an external surface (HTTP response,
  chat message). Full detail is logged server-side; external surfaces receive a
  generic message or the exception type name only.
- **FR-018** A preflight command MUST verify a configured provider end-to-end:
  authentication, a tool call, a structured output, and a stream.

### Key entities

| Entity | Description |
|---|---|
| **Provider** | A vendor endpoint with credentials, base URL, and capability metadata |
| **Transport** | How requests reach the provider — direct SDK or LiteLLM |
| **ModelDescriptor** | Context window, output limit, feature support flags, pricing |
| **InvokeRequest / InvokeResult** | Provider-neutral request and response, including tool calls and usage |
| **FailureClass** | The closed classification taxonomy |
| **UsageRecord** | Token counts and computed cost at call, turn, and run scope |
| **SchemaNormaliser** | Per-provider rewrite rules applied to tool schemas |

## Success criteria

- **SC-001** The contract suite passes for all nine providers using recorded
  fixtures, on every PR, consuming no live tokens.
- **SC-002** The combined-schema normalisation test passes for all nine providers
  with the full capability catalogue registered.
- **SC-003** A full investigation completes on Ollama with no network egress
  beyond the local model endpoint.
- **SC-004** Cost accounting is within 1% of the provider's own reported usage on
  a live smoke run for each provider with published pricing.
- **SC-005** The concurrent-turn race (acceptance scenario 6) is reproduced
  deterministically by a test with no threads, and passes.
- **SC-006** Adding a tenth provider requires touching only `core/llm/providers/`
  and a registry row — proven by adding one behind a test.

## Out of scope

- Prompt content and system-prompt construction (feature 004)
- Embeddings (feature 010 — separate provider path)
- Model selection policy per agent role (feature 013)
- Cross-model benchmarking (feature 028)

## Clarifications

| Question | Resolution |
|---|---|
| Is LiteLLM required? | No. It is an optional transport. The direct SDK path is the default and the one the contract suite treats as normative. |
| How is "parity" verified without burning tokens? | Recorded-fixture contract tests on every PR; live smoke on three providers per PR; the full cross-model run nightly (ADR 0008). |
| What happens when a provider adds a feature others lack? | It is exposed through the abstraction with an explicit capability flag; callers must handle absence. Never a silent behavioural difference. |
