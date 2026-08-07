"""Onboarding AWS Bedrock."""

from __future__ import annotations

from config.constants.llm import (
    AWS_ACCESS_KEY_ID_ENV,
    AWS_PROFILE_ENV,
    AWS_REGION_ENV,
    AWS_SECRET_ACCESS_KEY_ENV,
    AWS_SESSION_TOKEN_ENV,
    PROVIDER_AWS_BEDROCK,
)
from surfaces.cli.models import CredentialFieldSpec
from surfaces.cli.wizard.providers import ProviderOnboarding

ONBOARDING = ProviderOnboarding(
    provider_id=PROVIDER_AWS_BEDROCK,
    display_name="AWS Bedrock",
    default_model="anthropic.claude-sonnet-5-v1:0",
    fields=(
        CredentialFieldSpec(
            name=AWS_REGION_ENV,
            label="Region",
            secret=False,
            help="The region the model is enabled in, for example eu-west-1.",
        ),
        CredentialFieldSpec(
            name=AWS_PROFILE_ENV,
            label="Named profile",
            secret=False,
            required=False,
            help="Give a profile and leave the keys empty to use an existing session.",
        ),
        CredentialFieldSpec(
            name=AWS_ACCESS_KEY_ID_ENV,
            label="Access key id",
            secret=False,
            required=False,
        ),
        CredentialFieldSpec(
            name=AWS_SECRET_ACCESS_KEY_ENV,
            label="Secret access key",
            secret=True,
            required=False,
        ),
        CredentialFieldSpec(
            name=AWS_SESSION_TOKEN_ENV,
            label="Session token",
            secret=True,
            required=False,
            help="Only for temporary credentials.",
        ),
    ),
    guidance=(
        "Hosted in your own AWS account. Model access has to be enabled on the "
        "account before a request will succeed."
    ),
    where_to_get_it="IAM, or an existing named profile in your AWS configuration.",
    extras=("bedrock",),
)

__all__ = ["ONBOARDING"]
