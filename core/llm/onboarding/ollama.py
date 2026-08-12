"""Onboarding Ollama, and any other server speaking the same wire."""

from __future__ import annotations

from config.constants.llm import OLLAMA_BASE_URL_ENV, PROVIDER_OLLAMA
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_OLLAMA,
    display_name="Ollama or vLLM",
    default_model="llama4:70b",
    fields=(
        CredentialFieldSpec(
            name="base_url",
            environment_variable=OLLAMA_BASE_URL_ENV,
            label="Base URL",
            secret=False,
            help="For example http://127.0.0.1:11434/v1.",
        ),
    ),
    guidance=(
        "Runs entirely on infrastructure you control. A deployment configured "
        "this way emits no model traffic off-host at all, which is the whole "
        "point of the option being here rather than in a footnote."
    ),
    where_to_get_it="Your own machine. Nothing to obtain.",
    extras=("ollama",),
)

__all__ = ["ONBOARDING"]
