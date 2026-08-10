"""Onboarding Azure OpenAI."""

from __future__ import annotations

from config.constants.llm import (
    AZURE_OPENAI_API_KEY_ENV,
    AZURE_OPENAI_API_VERSION_ENV,
    AZURE_OPENAI_DEPLOYMENT_ENV,
    AZURE_OPENAI_ENDPOINT_ENV,
    PROVIDER_AZURE_OPENAI,
)
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_AZURE_OPENAI,
    display_name="Azure OpenAI",
    default_model="gpt-5",
    fields=(
        CredentialFieldSpec(
            name=AZURE_OPENAI_API_KEY_ENV,
            label="API key",
            secret=True,
        ),
        CredentialFieldSpec(
            name=AZURE_OPENAI_ENDPOINT_ENV,
            label="Endpoint",
            secret=False,
            help="For example https://my-resource.openai.azure.com.",
        ),
        CredentialFieldSpec(
            name=AZURE_OPENAI_DEPLOYMENT_ENV,
            label="Deployment name",
            secret=False,
            help="The name you gave the deployment, not the model name.",
        ),
        CredentialFieldSpec(
            name=AZURE_OPENAI_API_VERSION_ENV,
            label="API version",
            secret=False,
            required=False,
            help="Leave empty for the platform default.",
        ),
    ),
    guidance=(
        "Hosted in your own Azure tenant. Requests stay inside the region "
        "the resource is deployed to."
    ),
    where_to_get_it="The Azure portal, on the resource's Keys and Endpoint blade.",
    extras=("azure",),
)

__all__ = ["ONBOARDING"]
