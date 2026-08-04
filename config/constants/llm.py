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


__all__ = [
    "ANTHROPIC_API_KEY_ENV",
    "ANTHROPIC_BASE_URL_ENV",
    "AWS_BEDROCK_ENDPOINT_ENV",
    "AWS_REGION_ENV",
    "AZURE_OPENAI_API_KEY_ENV",
    "AZURE_OPENAI_API_VERSION_ENV",
    "AZURE_OPENAI_DEPLOYMENT_ENV",
    "AZURE_OPENAI_ENDPOINT_ENV",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PROVIDER",
    "GOOGLE_API_KEY_ENV",
    "GOOGLE_CLOUD_LOCATION_ENV",
    "GOOGLE_CLOUD_PROJECT_ENV",
    "LLM_CONNECT_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "LLM_RETRY_BASE_DELAY_SECONDS",
    "LLM_RETRY_MAX_DELAY_SECONDS",
    "LLM_STREAM_TIMEOUT_SECONDS",
    "LOCAL_PROVIDERS",
    "NINJASRE_LLM_MODEL_ENV",
    "NINJASRE_LLM_PROVIDER_ENV",
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
    "RETRYABLE_HTTP_STATUS_CODES",
    "SUPPORTED_PROVIDERS",
    "VLLM_BASE_URL_ENV",
]
