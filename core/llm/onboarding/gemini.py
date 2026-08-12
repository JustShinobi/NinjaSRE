"""Onboarding Google Gemini."""

from __future__ import annotations

from config.constants.llm import GOOGLE_API_KEY_ENV, PROVIDER_GOOGLE_GEMINI
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_GOOGLE_GEMINI,
    display_name="Google Gemini",
    default_model="gemini-3-pro",
    fields=(
        CredentialFieldSpec(
            name="api_key",
            environment_variable=GOOGLE_API_KEY_ENV,
            label="API key",
            secret=True,
        ),
    ),
    guidance="Hosted. Requests leave your infrastructure for Google's API.",
    where_to_get_it="aistudio.google.com, under API keys.",
    models=("gemini-3-pro", "gemini-3-flash"),
    extras=("google",),
)

__all__ = ["ONBOARDING"]
