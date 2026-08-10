"""Onboarding Anthropic."""

from __future__ import annotations

from config.constants.llm import ANTHROPIC_API_KEY_ENV, DEFAULT_MODEL_ID, PROVIDER_ANTHROPIC
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_ANTHROPIC,
    display_name="Anthropic",
    default_model=DEFAULT_MODEL_ID,
    fields=(
        CredentialFieldSpec(
            name=ANTHROPIC_API_KEY_ENV,
            label="API key",
            secret=True,
            help="Starts with 'sk-ant-'.",
        ),
    ),
    guidance="Hosted. Requests leave your infrastructure for Anthropic's API.",
    where_to_get_it="console.anthropic.com, under API keys.",
    models=("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"),
    extras=("anthropic",),
)

__all__ = ["ONBOARDING"]
