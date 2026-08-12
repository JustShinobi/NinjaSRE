"""Onboarding Google Gemini."""

from __future__ import annotations

from config.constants.llm import GOOGLE_API_KEY_ENV, PROVIDER_GOOGLE_GEMINI
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_GOOGLE_GEMINI,
    display_name="Google Gemini",
    default_model="gemini-pro-latest",
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
    # The aliases first: Google keeps them pointed at the current generation,
    # so a catalogue built on them stops rotting the moment a model ships.
    # This list previously named two models that did not exist, which an
    # operator only discovered on their first call.
    models=(
        "gemini-pro-latest",
        "gemini-flash-latest",
        "gemini-3.1-pro-preview",
        "gemini-3.6-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ),
    extras=("google",),
)

__all__ = ["ONBOARDING"]
