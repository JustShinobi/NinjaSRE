"""Onboarding Google Vertex AI."""

from __future__ import annotations

from config.constants.llm import (
    GOOGLE_APPLICATION_CREDENTIALS_ENV,
    GOOGLE_CLOUD_LOCATION_ENV,
    GOOGLE_CLOUD_PROJECT_ENV,
    PROVIDER_GOOGLE_VERTEX_AI,
)
from core.llm.onboarding import ProviderOnboarding
from platform.credentials.fields import CredentialFieldSpec

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_GOOGLE_VERTEX_AI,
    display_name="Google Vertex AI",
    default_model="gemini-3-pro",
    fields=(
        CredentialFieldSpec(
            name="project",
            environment_variable=GOOGLE_CLOUD_PROJECT_ENV,
            label="Project id",
            secret=False,
        ),
        CredentialFieldSpec(
            name="location",
            environment_variable=GOOGLE_CLOUD_LOCATION_ENV,
            label="Location",
            secret=False,
            help="For example europe-west4.",
        ),
        CredentialFieldSpec(
            name="service_account_file",
            environment_variable=GOOGLE_APPLICATION_CREDENTIALS_ENV,
            label="Service account key",
            secret=True,
            required=False,
            help="Paste the JSON key, or leave empty to use workload identity.",
        ),
    ),
    guidance=(
        "Hosted in your own Google Cloud project. Requests stay inside the "
        "location the endpoint is in."
    ),
    where_to_get_it="The Google Cloud console, under IAM and admin.",
    extras=("google",),
)

__all__ = ["ONBOARDING"]
