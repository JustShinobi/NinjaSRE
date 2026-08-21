"""Provider identifiers, environment-variable names, and transport defaults.

The nine supported providers. Adding a tenth means adding its identifier and its
env names here, and an adapter in ``core/llm/providers/`` — nothing else.

**These are names, never values.** A provider API key is resolved by the
credential vault and injected at the network boundary by the credential proxy
(Constitution Article IV). The agent process never reads these variables; the
names exist so the vault bootstrap and the operator's documentation agree on
what an operator is expected to set.

Per-provider model registries — context windows, pricing, capability flags —
belong to ``core/llm/``. What lives here is the platform-wide default and the
env names that override it.
"""

from __future__ import annotations

from typing import Final

# --- Provider identifiers ----------------------------------------------------

PROVIDER_ANTHROPIC: Final = "anthropic"
PROVIDER_OPENAI: Final = "openai"
PROVIDER_AZURE_OPENAI: Final = "azure_openai"
PROVIDER_AWS_BEDROCK: Final = "aws_bedrock"
PROVIDER_GOOGLE_GEMINI: Final = "google_gemini"
PROVIDER_GOOGLE_VERTEX_AI: Final = "google_vertex_ai"
PROVIDER_OPENROUTER: Final = "openrouter"
PROVIDER_NVIDIA_NIM: Final = "nvidia_nim"
PROVIDER_OLLAMA: Final = "ollama"

#: Every supported provider.
SUPPORTED_PROVIDERS: Final[tuple[str, ...]] = (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
)

#: Providers that run entirely on operator-controlled infrastructure. A
#: deployment restricted to these emits no traffic off-host
#: (Constitution Articles VI and X).
LOCAL_PROVIDERS: Final[tuple[str, ...]] = (PROVIDER_OLLAMA,)

# --- Provider selection ------------------------------------------------------

NINJASRE_LLM_PROVIDER_ENV: Final = "NINJASRE_LLM_PROVIDER"
NINJASRE_LLM_MODEL_ENV: Final = "NINJASRE_LLM_MODEL"

#: Used when neither the effective config nor the environment names a model.
#: ``core/llm/`` owns the registry that maps this to a provider deployment.
DEFAULT_MODEL_ID: Final = "claude-sonnet-5"
DEFAULT_PROVIDER: Final = PROVIDER_ANTHROPIC

# --- Per-provider environment variable names ---------------------------------

ANTHROPIC_API_KEY_ENV: Final = "ANTHROPIC_API_KEY"
ANTHROPIC_BASE_URL_ENV: Final = "ANTHROPIC_BASE_URL"

OPENAI_API_KEY_ENV: Final = "OPENAI_API_KEY"
OPENAI_BASE_URL_ENV: Final = "OPENAI_BASE_URL"

AZURE_OPENAI_API_KEY_ENV: Final = "AZURE_OPENAI_API_KEY"
AZURE_OPENAI_ENDPOINT_ENV: Final = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_API_VERSION_ENV: Final = "AZURE_OPENAI_API_VERSION"
AZURE_OPENAI_DEPLOYMENT_ENV: Final = "AZURE_OPENAI_DEPLOYMENT"

AWS_REGION_ENV: Final = "AWS_REGION"
AWS_BEDROCK_ENDPOINT_ENV: Final = "AWS_BEDROCK_ENDPOINT"

GOOGLE_API_KEY_ENV: Final = "GOOGLE_API_KEY"
GOOGLE_CLOUD_PROJECT_ENV: Final = "GOOGLE_CLOUD_PROJECT"
GOOGLE_CLOUD_LOCATION_ENV: Final = "GOOGLE_CLOUD_LOCATION"

OPENROUTER_API_KEY_ENV: Final = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL_ENV: Final = "OPENROUTER_BASE_URL"

NVIDIA_API_KEY_ENV: Final = "NVIDIA_API_KEY"
NVIDIA_NIM_BASE_URL_ENV: Final = "NVIDIA_NIM_BASE_URL"

OLLAMA_BASE_URL_ENV: Final = "OLLAMA_BASE_URL"
VLLM_BASE_URL_ENV: Final = "VLLM_BASE_URL"

#: Bedrock and Vertex authenticate with a credential set rather than a single
#: key, so their names are listed individually — the resolver reads whichever
#: subset the deployment provides.
AWS_ACCESS_KEY_ID_ENV: Final = "AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY_ENV: Final = "AWS_SECRET_ACCESS_KEY"
AWS_SESSION_TOKEN_ENV: Final = "AWS_SESSION_TOKEN"
AWS_PROFILE_ENV: Final = "AWS_PROFILE"

GOOGLE_APPLICATION_CREDENTIALS_ENV: Final = "GOOGLE_APPLICATION_CREDENTIALS"

# --- Transports --------------------------------------------------------------

#: Requests reach a provider through its own SDK, which is the path the
#: contract suite treats as normative (ADR 0008).
TRANSPORT_SDK: Final = "sdk"

#: An optional proxy for operators already running one. Behaviourally
#: equivalent by contract test, never the default.
TRANSPORT_LITELLM: Final = "litellm"

SUPPORTED_TRANSPORTS: Final[tuple[str, ...]] = (TRANSPORT_SDK, TRANSPORT_LITELLM)
DEFAULT_TRANSPORT: Final = TRANSPORT_SDK

NINJASRE_LLM_TRANSPORT_ENV: Final = "NINJASRE_LLM_TRANSPORT"

# --- Transport defaults ------------------------------------------------------

LLM_CONNECT_TIMEOUT_SECONDS: Final[float] = 10.0
LLM_REQUEST_TIMEOUT_SECONDS: Final[float] = 120.0

#: Streaming turns hold the connection open for the whole generation, so they
#: get their own, longer ceiling.
LLM_STREAM_TIMEOUT_SECONDS: Final[float] = 600.0

LLM_MAX_RETRIES: Final[int] = 3
LLM_RETRY_BASE_DELAY_SECONDS: Final[float] = 1.0
LLM_RETRY_MAX_DELAY_SECONDS: Final[float] = 30.0

#: Only transient failures are retried. Anything else — a rejected schema, a
#: bad key — is reported rather than repeated.
RETRYABLE_HTTP_STATUS_CODES: Final[frozenset[int]] = frozenset({408, 409, 429, 500, 502, 503, 504})

#: Backoff is randomised within this fraction of the computed delay. Without it,
#: every turn that hit the same rate limit retries at the same instant and hits
#: it again together.
LLM_RETRY_JITTER_RATIO: Final[float] = 0.25

# --- Request budgeting -------------------------------------------------------

#: Held back from the context window when deciding whether a request fits. The
#: estimate below is approximate and a provider's own tokeniser is authoritative;
#: refusing slightly early is cheaper than a rejected turn mid-investigation.
LLM_CONTEXT_RESERVE_TOKENS: Final[int] = 1_024

#: Used only when no provider token count is available. English prose averages
#: close to four characters per token; the result is always flagged as an
#: estimate so no accounting treats it as measured.
CHARACTERS_PER_TOKEN_ESTIMATE: Final[int] = 4

#: A structured-output fallback parses model prose. Beyond this the text is not
#: a near-miss JSON document, it is something else, and scanning it further
#: only delays the failure.
MAX_STRUCTURED_PARSE_CHARS: Final[int] = 200_000

# --- Behaviour probing -------------------------------------------------------
#
# A model card that says "supports tools" frequently means "was trained on
# some", and an advertised context window is frequently not the one a quantised
# build can actually use. The probe measures each behaviour the runtime depends
# on instead of trusting either, and these are the bounds it measures within.

#: Output tokens one probe prompt may produce. Small on purpose: a probe is
#: asking whether the mechanism works, never whether the model is clever, and a
#: suite an operator waits on is one they learn to skip.
MODEL_PROBE_MAX_OUTPUT_TOKENS: Final[int] = 64

#: Bisection steps allowed when measuring usable context. Each step is one call,
#: so this is the probe's whole cost ceiling for the most expensive behaviour;
#: eight steps resolve a 128k window to within about 500 tokens.
MODEL_PROBE_CONTEXT_STEPS: Final[int] = 8

#: Usable context is measured no finer than this. Resolving below it costs calls
#: to refine a number the character estimate cannot carry anyway.
MODEL_PROBE_CONTEXT_RESOLUTION_TOKENS: Final[int] = 512

#: Probed models kept in the cache. One entry per model an endpoint serves;
#: beyond this the least recently probed is dropped and re-probed on demand.
MODEL_PROBE_CACHE_MAX_ENTRIES: Final[int] = 64

# --- Tool-call resilience ----------------------------------------------------
#
# Every bound here exists because a small local model reaches the same place a
# frontier model reaches, by a longer route. None of them is conditional on a
# provider: a frontier model that starts emitting its tool calls as prose is
# handled by exactly this code.

#: Corrections sent back to the model within one turn before the turn is given
#: up on. Two, because the first correction names the problem and the second
#: proves the model cannot act on being told.
MAX_TOOL_CALL_REPAIRS_PER_TURN: Final[int] = 2

#: Corrections across a whole run. Well under the iteration ceiling, so a model
#: that needs one every turn ends the run on this bound and says so, rather than
#: spending the whole iteration budget being corrected.
MAX_TOOL_CALL_REPAIRS_PER_RUN: Final[int] = 8

#: Recent calls examined when looking for a model stuck on one. Wide enough to
#: see through an interleaved second call, narrow enough to break out long
#: before the iteration ceiling would.
REPEATED_CALL_WINDOW: Final[int] = 4

#: Identical name-and-argument calls inside that window before the loop is
#: declared broken and the model is told.
MAX_IDENTICAL_CALLS_IN_WINDOW: Final[int] = 3

#: Wall-clock ceiling for one model call, enforced by the resilience layer
#: rather than by the transport. A transport that ignores its own timeout — a
#: machine swapping under load is the case that produced this — otherwise hangs
#: the run with nothing in the trace to say so.
MODEL_CALL_BUDGET_SECONDS: Final[float] = 180.0

#: Ceiling for one endpoint health check. Far below the call budget: the
#: question is whether the endpoint answers at all, and an endpoint that needs a
#: minute to say "yes" has already answered "no".
ENDPOINT_HEALTH_TIMEOUT_SECONDS: Final[float] = 15.0

# --- Model registry ----------------------------------------------------------

#: Published prices change. A descriptor older than this is reported as stale so
#: cost accounting is corrected before anyone builds a budget on it.
MODEL_PRICING_MAX_AGE_DAYS: Final[int] = 180

#: Pricing is published per million tokens; the registry stores it that way and
#: divides once, here, rather than at every call site.
TOKENS_PER_PRICING_UNIT: Final[int] = 1_000_000

# --- Model listing -------------------------------------------------------------
#
# A provider's own endpoint is asked what it currently serves, rather than
# trusting the static registry above, which drifts the day a vendor ships a
# model this build has never heard of. The bounds below govern that call.

#: How long a fetched listing is trusted before the next read asks again.
#: Short enough that a key rotated an hour ago is reflected the same day,
#: long enough that opening the same screen three times in a minute does not
#: call the vendor three times.
MODEL_LISTING_CACHE_TTL_SECONDS: Final[float] = 300.0

#: How long a listing call may take before it is treated as unavailable and the
#: caller falls back to the static registry. A screen must not hang on a vendor
#: having a slow day.
MODEL_LISTING_FETCH_TIMEOUT_SECONDS: Final[float] = 10.0

#: Distinct providers whose listing this process holds in cache at once. Well
#: above the nine supported providers, so nothing here is a practical limit —
#: it exists to cap memory for a process that outlives many configuration
#: changes, not to ration a resource that is scarce today.
MODEL_LISTING_CACHE_MAX_ENTRIES: Final[int] = 64

#: Where Google's Gemini API lists the models this deployment's key can reach.
GOOGLE_GENERATIVE_LANGUAGE_MODELS_URL: Final = (
    "https://generativelanguage.googleapis.com/v1beta/models"
)


__all__ = [
    "ANTHROPIC_API_KEY_ENV",
    "ANTHROPIC_BASE_URL_ENV",
    "AWS_ACCESS_KEY_ID_ENV",
    "AWS_BEDROCK_ENDPOINT_ENV",
    "AWS_PROFILE_ENV",
    "AWS_REGION_ENV",
    "AWS_SECRET_ACCESS_KEY_ENV",
    "AWS_SESSION_TOKEN_ENV",
    "AZURE_OPENAI_API_KEY_ENV",
    "AZURE_OPENAI_API_VERSION_ENV",
    "AZURE_OPENAI_DEPLOYMENT_ENV",
    "AZURE_OPENAI_ENDPOINT_ENV",
    "CHARACTERS_PER_TOKEN_ESTIMATE",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PROVIDER",
    "DEFAULT_TRANSPORT",
    "ENDPOINT_HEALTH_TIMEOUT_SECONDS",
    "GOOGLE_API_KEY_ENV",
    "GOOGLE_APPLICATION_CREDENTIALS_ENV",
    "GOOGLE_CLOUD_LOCATION_ENV",
    "GOOGLE_CLOUD_PROJECT_ENV",
    "GOOGLE_GENERATIVE_LANGUAGE_MODELS_URL",
    "LLM_CONNECT_TIMEOUT_SECONDS",
    "LLM_CONTEXT_RESERVE_TOKENS",
    "LLM_MAX_RETRIES",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "LLM_RETRY_BASE_DELAY_SECONDS",
    "LLM_RETRY_JITTER_RATIO",
    "LLM_RETRY_MAX_DELAY_SECONDS",
    "LLM_STREAM_TIMEOUT_SECONDS",
    "LOCAL_PROVIDERS",
    "MAX_IDENTICAL_CALLS_IN_WINDOW",
    "MAX_STRUCTURED_PARSE_CHARS",
    "MAX_TOOL_CALL_REPAIRS_PER_RUN",
    "MAX_TOOL_CALL_REPAIRS_PER_TURN",
    "MODEL_CALL_BUDGET_SECONDS",
    "MODEL_LISTING_CACHE_MAX_ENTRIES",
    "MODEL_LISTING_CACHE_TTL_SECONDS",
    "MODEL_LISTING_FETCH_TIMEOUT_SECONDS",
    "MODEL_PRICING_MAX_AGE_DAYS",
    "MODEL_PROBE_CACHE_MAX_ENTRIES",
    "MODEL_PROBE_CONTEXT_RESOLUTION_TOKENS",
    "MODEL_PROBE_CONTEXT_STEPS",
    "MODEL_PROBE_MAX_OUTPUT_TOKENS",
    "NINJASRE_LLM_MODEL_ENV",
    "NINJASRE_LLM_PROVIDER_ENV",
    "NINJASRE_LLM_TRANSPORT_ENV",
    "NVIDIA_API_KEY_ENV",
    "NVIDIA_NIM_BASE_URL_ENV",
    "OLLAMA_BASE_URL_ENV",
    "OPENAI_API_KEY_ENV",
    "OPENAI_BASE_URL_ENV",
    "OPENROUTER_API_KEY_ENV",
    "OPENROUTER_BASE_URL_ENV",
    "PROVIDER_ANTHROPIC",
    "PROVIDER_AWS_BEDROCK",
    "PROVIDER_AZURE_OPENAI",
    "PROVIDER_GOOGLE_GEMINI",
    "PROVIDER_GOOGLE_VERTEX_AI",
    "PROVIDER_NVIDIA_NIM",
    "PROVIDER_OLLAMA",
    "PROVIDER_OPENAI",
    "PROVIDER_OPENROUTER",
    "REPEATED_CALL_WINDOW",
    "RETRYABLE_HTTP_STATUS_CODES",
    "SUPPORTED_PROVIDERS",
    "SUPPORTED_TRANSPORTS",
    "TOKENS_PER_PRICING_UNIT",
    "TRANSPORT_LITELLM",
    "TRANSPORT_SDK",
    "VLLM_BASE_URL_ENV",
]
