"""The Gemini models this deployment offers, against the ones that exist.

Onboarding offered `gemini-3-pro` and `gemini-3-flash`. Neither is a model. The
provider lists thirty-three and those two are not among them, so an operator who
picked either on their first day got a deployment that authenticated and then
failed on its first call — the worst shape a first-day failure can take, because
the credential looks fine.

The registry, meanwhile, knew only `gemini-2.5-pro`. Two lists, both wrong, in
different directions: onboarding offered models that do not exist, and the
registry refused models that do.

**The defaults are the aliases.** `gemini-pro-latest` and `gemini-flash-latest`
are what Google keeps pointed at the current generation, so a catalogue built on
them stops rotting the moment a new model ships. A pinned identifier is right
for a deployment that has a reason to pin; it is wrong as the shipped default,
which is exactly how this list came to name two models that no longer exist.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

#: What the provider actually lists, read from the API with a real key. Not the
#: whole thirty-three: the ones a catalogue would sensibly offer.
REAL_MODELS = frozenset(
    {
        "gemini-pro-latest",
        "gemini-flash-latest",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
        "gemini-3.6-flash",
    }
)

#: What onboarding offered, and what does not exist.
RETIRED = frozenset({"gemini-3-pro", "gemini-3-flash"})


def test_onboarding_offers_no_model_that_does_not_exist() -> None:
    """The defect: both offered identifiers were absent from the provider."""
    from core.llm.onboarding.gemini import ONBOARDING

    assert not (set(ONBOARDING.models) & RETIRED)


def test_every_offered_model_is_one_the_provider_lists() -> None:
    from core.llm.onboarding.gemini import ONBOARDING

    assert set(ONBOARDING.models) <= REAL_MODELS


def test_the_default_is_an_alias_rather_than_a_pinned_generation() -> None:
    """A pinned default is how this list came to name two models that had been
    retired: nothing fails until somebody picks it, and by then it is shipped."""
    from core.llm.onboarding.gemini import ONBOARDING

    assert ONBOARDING.default_model.endswith("-latest")


def test_the_registry_knows_every_model_onboarding_offers() -> None:
    """Onboarding offering a model the registry does not carry is the same
    defect from the other side: the choice is accepted and then unusable."""
    from config.constants.llm import PROVIDER_GOOGLE_GEMINI
    from core.llm.onboarding.gemini import ONBOARDING
    from core.llm.registry import build_default_registry

    registry = build_default_registry()
    known = {model.model_id for model in registry.for_provider(PROVIDER_GOOGLE_GEMINI)}

    assert set(ONBOARDING.models) <= known


def test_the_registry_carries_the_limits_the_provider_reports() -> None:
    """A context window this system believes and the provider does not is a
    truncation nobody predicted."""
    from config.constants.llm import PROVIDER_GOOGLE_GEMINI
    from core.llm.registry import build_default_registry

    registry = build_default_registry()
    by_id = {model.model_id: model for model in registry.for_provider(PROVIDER_GOOGLE_GEMINI)}

    for model_id in ("gemini-pro-latest", "gemini-flash-latest"):
        assert by_id[model_id].context_window == 1_048_576
        assert by_id[model_id].max_output_tokens == 65_536


def test_the_provider_default_is_a_model_the_registry_carries() -> None:
    from config.constants.llm import PROVIDER_GOOGLE_GEMINI
    from core.llm.registry import build_default_registry

    registry = build_default_registry()
    provider = registry.provider(PROVIDER_GOOGLE_GEMINI)
    known = {model.model_id for model in registry.for_provider(PROVIDER_GOOGLE_GEMINI)}

    assert provider is not None
    assert provider.default_model_id in known
