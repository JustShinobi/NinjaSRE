"""Onboarding OpenAI."""

from __future__ import annotations

from config.constants.llm import OPENAI_API_KEY_ENV, OPENAI_BASE_URL_ENV, PROVIDER_OPENAI
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_OPENAI,
    display_name="OpenAI",
    default_model="gpt-5",
    fields=(
        CredentialFieldSpec(
            name=OPENAI_API_KEY_ENV,
            label="API key",
            secret=True,
            help="Starts with 'sk-'.",
        ),
        CredentialFieldSpec(
            name=OPENAI_BASE_URL_ENV,
            label="Base URL",
            secret=False,
            required=False,
            help="Leave empty unless you front the API with a gateway.",
        ),
    ),
    guidance="Hosted. Requests leave your infrastructure for OpenAI's API.",
    where_to_get_it="platform.openai.com, under API keys.",
    models=("gpt-5", "gpt-5-mini", "o4"),
    extras=("openai",),
)

__all__ = ["ONBOARDING"]
