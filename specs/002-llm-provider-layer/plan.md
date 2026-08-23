# Plan — 002 LLM Provider Layer

## Summary

Port Tracer's provider abstraction into `core/llm/`, extend it to full parity
across nine providers, and back it with a contract suite that runs on recorded
fixtures. The schema-normalisation layer is the highest-risk component and is
built test-first against the combined capability catalogue.

## Technical context

| Aspect | Choice |
|---|---|
| Abstraction | `LLMClient` Protocol; per-provider adapters |
| Transports | Direct vendor SDK (default), LiteLLM (optional extra) |
| Structured output | Native → tool-call coercion → prose parsing, in that order |
| Retry | `tenacity`-style exponential backoff with jitter, implemented in-house to keep classification coupled to the retry decision |
| Fixtures | `pytest-recording` / VCR-style cassettes, secrets scrubbed at record time |
| Token counting | Provider-reported where available; `tiktoken`-compatible estimation as fallback, flagged as estimated |
| Credentials | Injected `CredentialResolver` port; the vault implementation lands in 007 |

## Constitution check

| Article | Satisfaction |
|---|---|
| I | Every call is recorded with usage, mechanism, and classification into the run trace |
| II | Attempt ceilings, timeouts, and context-window limits are named constants in `config/constants/llm.py` |
| III | N/A |
| IV | FR-015 — no call site reads a credential; resolution goes through the port |
| V | The layer is runtime-agnostic; the SDK runtime adapter consumes it identically |
| VI | **This is the feature.** FR-001, FR-002, SC-003 |
| VII | Usage records feed cost axes in the evaluation suite |
| VIII | `core/llm/` is tier 3; imports only `config` and `platform` |
| IX | Schema normalisation is what makes bounded typed capabilities work across providers |
| X | No provider call leaves the host unless the operator configured a cloud provider |
| XI | Usage records persist through `RunTraceStore` (feature 006) |
| XII | Contract suite and combined-schema test written before adapters |
| XIII | Provenance headers on all ported modules |

**Violations:** none.

## Project structure

```
core/llm/
├── __init__.py                  # get_llm() facade
├── types.py                     # LLMClient protocol, InvokeRequest/Result, ToolCall
├── factory.py                   # role → provider → client resolution
├── registry.py                  # ModelDescriptor catalogue
├── schema.py                    # SchemaNormaliser + per-provider rules
├── failures.py                  # FailureClass taxonomy + classification
├── retry.py                     # backoff policy coupled to classification
├── usage.py                     # UsageRecord, cost computation
├── cache.py                     # prompt-cache markers + uncached retry
├── credentials.py               # CredentialResolver port
├── preflight.py                 # end-to-end provider verification
├── internal/
│   ├── client_cache.py          # per-role instance cache
│   └── client_cache_key.py
├── providers/
│   ├── anthropic.py  openai.py  azure_openai.py  bedrock.py
│   ├── gemini.py     vertex.py  openrouter.py    nvidia_nim.py
│   ├── ollama.py
│   └── openai_compat.py         # shared base for OpenAI-wire-compatible providers
├── transports/
│   ├── sdk/                     # direct vendor SDK calls
│   └── litellm/                 # optional proxy transport
└── structured/
    ├── native.py  tool_coercion.py  prose_parsing.py
```

## Provider matrix

| Provider | Transport | Tool calls | Structured output | Streaming | Parallel calls | Prompt cache | Reasoning effort |
|---|---|---|---|---|---|---|---|
| Anthropic | SDK | native | native | yes | yes | yes | yes |
| OpenAI | SDK (Chat + Responses) | native | native | yes | yes | yes | yes |
| Azure OpenAI | SDK | native | native | yes | yes | partial | yes |
| AWS Bedrock | Converse API | native | tool coercion | yes | model-dependent | model-dependent | model-dependent |
| Gemini | SDK | native | native | yes | yes | yes | no |
| Vertex AI | SDK | native | native | yes | yes | yes | no |
| OpenRouter | OpenAI-compatible | native | model-dependent | yes | model-dependent | no | passthrough |
| NVIDIA NIM | OpenAI-compatible | native | model-dependent | yes | model-dependent | no | no |
| Ollama / vLLM | OpenAI-compatible | native | tool coercion | yes | no | no | no |

Cells marked model-dependent are resolved from `ModelDescriptor` at call time, not
assumed.

## Implementation phases

### Phase 1 — Contracts and taxonomy (test-first)
`types.py`, `failures.py`, the contract test suite skeleton parameterised over
providers, and the combined-schema normalisation test. All red.

### Phase 2 — Schema normalisation
Per-provider rewrite rules driven by the failing combined-schema test. This lands
before any adapter so adapters are written against a working normaliser.

### Phase 3 — Reference adapter
Anthropic end to end: invoke, stream, structured, usage, cache, reasoning effort.
Record fixtures. Contract suite green for one provider.

### Phase 4 — OpenAI-wire family
`openai_compat.py` base, then OpenAI, Azure OpenAI, OpenRouter, NVIDIA NIM, Ollama.
Five providers from one base plus per-provider deltas.

### Phase 5 — Remaining adapters
Bedrock (Converse, model-id mapping), Gemini, Vertex AI.

### Phase 6 — Cross-cutting
Retry with classification coupling, usage and cost accounting, client cache with
the request-local state capture (FR-011), preflight command, LiteLLM transport.

### Phase 7 — Hardening
Concurrent-turn race test, context-window guard, external-surface error redaction,
tenth-provider proof (SC-006).

## Complexity tracking

| Item | Justification |
|---|---|
| Two transports (SDK + LiteLLM) | LiteLLM is genuinely useful for operators already running it, but placing it on the default path means debugging a third party's dialect translation. Keeping the SDK default and LiteLLM optional gives the benefit without the risk. Behavioural equivalence is a contract test. |
| In-house retry rather than `tenacity` | The retry decision depends on the failure classification, and the classification depends on provider-specific response shapes. Coupling them in one module keeps the decision auditable; a generic retry decorator would push classification to call sites. |
| Prose-parsing fallback for structured output | Undesirable but necessary: quantised local models routinely produce near-JSON. Recording which mechanism was used means the evaluation suite can measure how often the fallback fires. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `core/llm/providers/` | ADOPT |
| Tracer | `core/llm/shared/tool_schema_normalize.py` | ADOPT → `core/llm/schema.py` |
| Tracer | `core/llm/shared/{llm_retry,structured_output,usage}.py` | ADOPT |
| Tracer | `core/llm/transports/{sdk,litellm}/` | ADAPT |
| Tracer | `core/llm/transports/sdk/anthropic_cache.py` | ADAPT → `cache.py`, with the shared-client race fixed by construction |
| Tracer | `core/llm/failure_classification.py`, `core/llm_invoke_errors.py` | ADOPT → `failures.py` |
| Tracer | `core/llm/internal/client_cache*.py` | ADAPT |
| Tracer | `tests/synthetic/llm_provider_preflight.py` | ADAPT → `preflight.py` |
| Tracer | `core/agent_harness/accounting/` | ADAPT → `usage.py` |

## Risks

| Risk | Mitigation |
|---|---|
| Vendor API drift breaks adapters silently | Recorded fixtures are refreshed on a schedule; a nightly live smoke on all nine catches drift within a day |
| Combined-schema failure only appears with a large catalogue | The normalisation test loads the **entire** registered catalogue, and Wave 6 grows it to ~85 integrations — the test scales with the risk |
| Local models produce malformed tool calls | Tool-coercion and prose-parsing fallbacks, with the fallback rate exposed as an evaluation metric so degradation is visible, not hidden |
| Cost accounting drifts as pricing changes | Pricing lives in the registry with an explicit `pricing_as_of` date; a test warns when a descriptor is older than 180 days |
