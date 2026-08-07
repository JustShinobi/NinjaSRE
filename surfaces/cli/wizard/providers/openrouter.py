"""Onboarding OpenRouter."""

from __future__ import annotations

from config.constants.llm import (
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL_ENV,
    PROVIDER_OPENROUTER,
)
from surfaces.cli.models import CredentialFieldSpec
from surfaces.cli.wizard.providers import ProviderOnboarding

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_OPENROUTER,
    display_name="OpenRouter",
    default_model="anthropic/claude-sonnet-5",
    fields=(
        CredentialFieldSpec(
            name=OPENROUTER_API_KEY_ENV,
            label="API key",
            secret=True,
            help="Starts with 'sk-or-'.",
        ),
        CredentialFieldSpec(
            name=OPENROUTER_BASE_URL_ENV,
            label="Base URL",
            secret=False,
            required=False,
            help="Leave empty for the default.",
        ),
    ),
    guidance=(
        "Hosted, and it routes onward to whichever provider serves the model "
        "you name. Two hops rather than one, which is worth knowing before you "
        "point it at anything sensitive."
    ),
    where_to_get_it="openrouter.ai, under keys.",
    extras=("openrouter",),
)

__all__ = ["ONBOARDING"]
