# Tasks — 002 LLM Provider Layer

## Phase 1 — Contracts and taxonomy (test-first)

- **T001** `core/llm/types.py`: `LLMClient` Protocol (`invoke`, `stream`,
  `invoke_structured`, `count_tokens`), `InvokeRequest`, `InvokeResult`,
  `ToolCall`, `ToolResult`, `StreamEvent`. Docstring-only Protocol bodies.
- **T002** `core/llm/failures.py`: `FailureClass` enum and the
  `classify(exc, response) -> FailureClass` contract. Tests first.
- **T003** `core/llm/registry.py`: `ModelDescriptor` with context window, max
  output, feature flags, pricing, `pricing_as_of`.
- **T004** Test asserting no descriptor is older than 180 days (warning-level).
- **T005** `tests/contract/llm/conftest.py`: fixture parameterising the whole suite
  over the nine providers, with cassette recording and secret scrubbing.
- **T006** Write the contract suite (all red): tool calling, structured output,
  streaming, retry, classification, usage accounting, context-limit guard.
- **T007** Write the combined-schema normalisation test (red): load every
  registered capability schema and assert acceptance by each provider's
  validator.

## Phase 2 — Schema normalisation

- **T008** `core/llm/schema.py`: `SchemaNormaliser` with a per-provider rule chain.
- **T009** Rule: collapse union types (`"type": ["object","null"]`) to the
  provider-accepted form.
- **T010** [P] Rule: flatten unsupported nested `anyOf`/`oneOf`.
- **T011** [P] Rule: normalise `additionalProperties` handling.
- **T012** [P] Rule: strip or map unsupported `format` values.
- **T013** [P] Rule: relocate `required` to the position each provider expects.
- **T014** [P] Rule: enforce per-provider name and description length limits.
- **T015** Property test: normalisation is idempotent and never loses a required
  field.
- **T016** Confirm T007 green for the reference provider.

## Phase 3 — Reference adapter (Anthropic)

- **T017** `core/llm/providers/anthropic.py`: invoke and stream.
- **T018** Structured output via `core/llm/structured/native.py`.
- **T019** `core/llm/usage.py`: `UsageRecord`, cost computation, cached-token
  accounting.
- **T020** `core/llm/cache.py`: prompt-cache markers plus the single uncached
  retry on marker rejection (FR-012).
- **T021** Reasoning-effort passthrough.
- **T022** Record fixtures; contract suite green for Anthropic (part of SC-001).

## Phase 4 — OpenAI-wire family

- **T023** `core/llm/providers/openai_compat.py`: shared base for OpenAI-wire
  providers.
- **T024** `openai.py`: Chat Completions and Responses transports, native
  structured output, prompt cache.
- **T025** [P] `azure_openai.py`: deployment-name addressing, separate auth,
  API-version pinning.
- **T026** [P] `openrouter.py`: model routing, passthrough of reasoning controls.
- **T027** [P] `nvidia_nim.py`.
- **T028** `ollama.py`: local endpoint, tool-coercion structured output, no
  parallel calls.
- **T029** `core/llm/structured/tool_coercion.py` and `prose_parsing.py`, with the
  mechanism recorded in `InvokeResult`.
- **T030** Record fixtures; contract suite green for all five.

## Phase 5 — Remaining adapters

- **T031** `bedrock.py`: Converse API, model-id and inference-profile mapping,
  region resolution.
- **T032** [P] `gemini.py`.
- **T033** [P] `vertex.py`: service-account auth with mid-run refresh.
- **T034** Record fixtures; contract suite green for all nine (SC-001).
- **T035** Confirm the combined-schema test green for all nine (SC-002).

## Phase 6 — Cross-cutting

- **T036** `core/llm/retry.py`: exponential backoff with jitter, ceiling from
  `config/constants/llm.py`, no retry on non-transient classes.
- **T037** Test: each `FailureClass` produces the correct retry decision.
- **T038** `core/llm/credentials.py`: `CredentialResolver` port plus an
  environment-backed reference implementation to be replaced in feature 007.
- **T039** CI check: no vendor SDK imported outside `core/llm/` (FR-002).
- **T040** `core/llm/internal/client_cache.py` with the cache key, and
  request-local capture of any state an error handler consults (FR-011).
- **T041** Deterministic, thread-free reproduction of the concurrent-turn race;
  confirm it passes (SC-005).
- **T042** `core/llm/factory.py`: `get_llm(role)` resolving role → provider →
  model → client.
- **T043** Context-window guard: refuse or truncate before dispatch when the
  request exceeds `ModelDescriptor.context_window`.
- **T044** External-surface error redaction (FR-017) with a test asserting no
  exception detail escapes.
- **T045** `core/llm/transports/litellm/`: optional transport behind an extra.
- **T046** Equivalence test: SDK and LiteLLM transports produce equivalent
  `InvokeResult` for the same request (FR-014).

## Phase 7 — Hardening and verification

- **T047** `core/llm/preflight.py`: auth, tool call, structured output, and stream
  verification per provider.
- **T048** CLI-invocable preflight (surfaces wire it in feature 019).
- **T049** Live smoke run per provider; validate cost accounting within 1%
  (SC-004).
- **T050** Full investigation on Ollama with egress blocked at the network level
  (SC-003).
- **T051** Add a tenth provider behind a feature flag touching only
  `providers/` and a registry row; prove SC-006, then remove.
- **T052** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Contract suite green for all nine providers on recorded fixtures (SC-001)
- [ ] Combined-schema test green with the full catalogue (SC-002)
- [ ] Ollama investigation completes with no external egress (SC-003)
- [ ] Cost accounting within 1% on live smoke (SC-004)
- [ ] Concurrent-turn race test deterministic and passing (SC-005)
- [ ] Tenth-provider proof recorded (SC-006)
- [ ] No vendor SDK imported outside `core/llm/`
- [ ] `make verify` green
