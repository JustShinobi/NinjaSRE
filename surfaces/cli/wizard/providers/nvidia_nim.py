"""Onboarding NVIDIA NIM."""

from __future__ import annotations

from config.constants.llm import (
    NVIDIA_API_KEY_ENV,
    NVIDIA_NIM_BASE_URL_ENV,
    PROVIDER_NVIDIA_NIM,
)
from surfaces.cli.models import CredentialFieldSpec
from surfaces.cli.wizard.providers import ProviderOnboarding

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_NVIDIA_NIM,
    display_name="NVIDIA NIM",
    default_model="meta/llama-4-70b-instruct",
    fields=(
        CredentialFieldSpec(
            name=NVIDIA_NIM_BASE_URL_ENV,
            label="Base URL",
            secret=False,
            help="Your own NIM endpoint, or the hosted catalogue endpoint.",
        ),
        CredentialFieldSpec(
            name=NVIDIA_API_KEY_ENV,
            label="API key",
            secret=True,
            required=False,
            help="Not needed for a NIM you run yourself without authentication.",
        ),
    ),
    guidance=(
        "Runs wherever you deploy it. Pointed at your own NIM container, "
        "nothing leaves your infrastructure."
    ),
    where_to_get_it="build.nvidia.com, or your own NIM deployment.",
    extras=("nvidia",),
)

__all__ = ["ONBOARDING"]
