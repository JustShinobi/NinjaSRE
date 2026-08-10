"""What a provider needs to be set up, read from below the surfaces.

The descriptors used to live inside the CLI's wizard package. Two surfaces need
them now — the wizard still, and the API's ``/v1/providers`` family — and two
tier-1 packages may not import each other, so they moved down beside the
adapters they describe.

This is the characterisation of what moved: nine providers, in the order the
constants declare, each saying what to enter, where to get it, and what to run.
Nothing about the behaviour changed, which is what these assertions are for.
"""

from __future__ import annotations

import pytest

from config.constants.llm import LOCAL_PROVIDERS, SUPPORTED_PROVIDERS
from core.llm.onboarding import (
    EXPECTED_PROVIDERS,
    ProviderOnboarding,
    UnknownProviderError,
    all_onboardings,
    onboarding_for,
    provider_names,
)
from core.llm.registry import default_registry
from platform.credentials.fields import CredentialFieldSpec

pytestmark = pytest.mark.unit


def test_every_supported_provider_declares_an_onboarding() -> None:
    onboardable = {onboarding.provider_id for onboarding in all_onboardings()}
    missing = set(EXPECTED_PROVIDERS) - onboardable

    assert not missing, (
        f"these providers have an adapter but no onboarding: {sorted(missing)}. "
        f"A provider nobody can configure is a provider nobody reaches."
    )


def test_the_providers_come_back_in_the_documented_order() -> None:
    """Declared order rather than alphabetical, at the new location as at the old."""
    assert tuple(provider_names()) == SUPPORTED_PROVIDERS
    assert len(all_onboardings()) == len(SUPPORTED_PROVIDERS)


def test_every_onboarding_says_what_to_enter_and_where_to_get_it() -> None:
    for onboarding in all_onboardings():
        assert onboarding.fields, f"{onboarding.provider_id} declares no fields"
        assert onboarding.where_to_get_it, f"{onboarding.provider_id} says nothing about where"
        assert onboarding.default_model, f"{onboarding.provider_id} names no default model"


def test_the_local_provider_is_marked_local_and_the_others_are_not() -> None:
    for onboarding in all_onboardings():
        assert onboarding.local == (onboarding.provider_id in LOCAL_PROVIDERS)


def test_a_field_spec_carries_a_name_and_never_a_value() -> None:
    """The type is what makes a descriptor safe to serve over HTTP.

    A field says what to ask for and whether the prompt echoes. There is no
    attribute a stored credential could be read back into, which is why
    ``GET /v1/providers/{id}`` can return the whole descriptor.
    """
    for onboarding in all_onboardings():
        for declared in onboarding.fields:
            assert isinstance(declared, CredentialFieldSpec)
            assert declared.name
            assert set(declared.to_record()) == {"name", "label", "secret", "required", "help"}


def test_an_unknown_provider_is_refused_naming_the_ones_that_exist() -> None:
    """Refused rather than defaulted, and the refusal is a list somebody can pick from."""
    with pytest.raises(UnknownProviderError, match="anthropik") as refused:
        onboarding_for("anthropik")

    assert "anthropic" in str(refused.value)
    assert refused.value.known == tuple(sorted(SUPPORTED_PROVIDERS))


def test_every_onboarded_provider_is_one_the_registry_can_build() -> None:
    """The descriptor and the adapter are two halves of the same claim.

    An onboarding for a provider the factory cannot instantiate is a first run
    that finishes and a deployment that cannot think.
    """
    known = set(default_registry().provider_ids())

    for onboarding in all_onboardings():
        assert onboarding.provider_id in known


def test_a_descriptor_is_a_value_with_no_behaviour_to_configure() -> None:
    """Frozen, so a caller cannot edit the deployment's provider list in passing."""
    anthropic = onboarding_for("anthropic")

    assert isinstance(anthropic, ProviderOnboarding)
    with pytest.raises(AttributeError):
        anthropic.default_model = "something-else"  # type: ignore[misc]
