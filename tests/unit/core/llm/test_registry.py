"""The registry answers what a model can do before a call is made.

Two properties matter more than the catalogue's contents. A descriptor whose
pricing nobody has checked in six months is reported as stale rather than
quietly used, and cost for a model with no published pricing is ``None`` rather
than zero — a fabricated cost is worse than an absent one.
"""

from __future__ import annotations

import warnings
from datetime import date

import pytest

from config.constants.llm import MODEL_PRICING_MAX_AGE_DAYS, SUPPORTED_PROVIDERS
from core.llm.registry import (
    ModelDescriptor,
    ModelRegistry,
    Pricing,
    UnknownModelError,
    build_default_registry,
    default_registry,
)

pytestmark = pytest.mark.unit


def _descriptor(**overrides: object) -> ModelDescriptor:
    fields: dict[str, object] = {
        "model_id": "test-model",
        "provider_id": "anthropic",
        "context_window": 200_000,
        "max_output_tokens": 8_192,
        "pricing": Pricing(input_per_million=1.0, output_per_million=2.0),
        "pricing_as_of": date(2026, 8, 4),
    }
    fields.update(overrides)
    return ModelDescriptor(**fields)  # type: ignore[arg-type]


def test_every_supported_provider_has_at_least_one_model() -> None:
    registry = default_registry()
    for provider_id in SUPPORTED_PROVIDERS:
        assert registry.for_provider(provider_id), f"{provider_id} has no registered model"


def test_the_catalogue_declares_a_default_model_per_provider() -> None:
    registry = default_registry()
    for provider_id in SUPPORTED_PROVIDERS:
        descriptor = registry.default_for_provider(provider_id)
        assert descriptor.provider_id == provider_id


def test_lookup_by_provider_and_model() -> None:
    registry = ModelRegistry()
    registry.register(_descriptor())

    assert registry.get("anthropic", "test-model").context_window == 200_000


def test_an_alias_resolves_to_the_same_descriptor() -> None:
    registry = ModelRegistry()
    registry.register(_descriptor(aliases=("test-model-latest",)))

    assert registry.get("anthropic", "test-model-latest").model_id == "test-model"


def test_an_unknown_model_raises_rather_than_guessing() -> None:
    registry = ModelRegistry()
    with pytest.raises(UnknownModelError):
        registry.get("anthropic", "no-such-model")


def test_registering_a_new_provider_needs_only_a_row() -> None:
    registry = build_default_registry()
    registry.register(_descriptor(provider_id="tenth", model_id="tenth-model"))

    assert registry.get("tenth", "tenth-model").provider_id == "tenth"
    assert "tenth" in registry.provider_ids()


def test_pricing_older_than_the_ceiling_is_reported_as_stale() -> None:
    registry = ModelRegistry()
    registry.register(_descriptor(model_id="fresh", pricing_as_of=date(2026, 8, 1)))
    registry.register(_descriptor(model_id="ancient", pricing_as_of=date(2020, 1, 1)))

    stale = registry.stale_pricing(as_of=date(2026, 8, 4))

    assert [descriptor.model_id for descriptor in stale] == ["ancient"]


def test_a_descriptor_with_no_pricing_is_not_stale_it_is_unpriced() -> None:
    registry = ModelRegistry()
    registry.register(_descriptor(model_id="unpriced", pricing=None, pricing_as_of=None))

    assert registry.stale_pricing(as_of=date(2026, 8, 4)) == ()


def test_the_shipped_catalogue_pricing_is_reported_when_it_ages() -> None:
    """Warning, not failure.

    Published prices drift on the vendor's schedule, not on ours. Failing the
    build on the 181st day would break a change that had nothing to do with
    pricing; a warning in the summary reaches the same person without doing
    that. The mechanism itself is asserted above, deterministically.
    """
    stale = default_registry().stale_pricing(as_of=date.today())

    if stale:
        warnings.warn(
            f"{len(stale)} model descriptor(s) carry pricing older than "
            f"{MODEL_PRICING_MAX_AGE_DAYS} days: "
            f"{', '.join(descriptor.model_id for descriptor in stale)}",
            stacklevel=1,
        )


def test_a_local_model_is_free_and_says_so() -> None:
    descriptor = default_registry().default_for_provider("ollama")
    assert descriptor.pricing is None
