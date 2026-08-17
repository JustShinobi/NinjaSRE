"""Curating a provider's own model listing, caching it, and falling back honestly.

The listing a provider's endpoint returns is not offered as-is: it is curated
down to models this platform can actually drive an investigation on, cached so
that opening a screen three times does not call the vendor three times, and
replaced by the static registry — labelled as such — whenever the endpoint
cannot answer the question at all.
"""

from __future__ import annotations

import pytest

from core.llm.catalogue import ModelOffering, curate
from core.llm.catalogue.cache import ModelCatalogueCache
from tools.mockplane.dataset.gemini_models import (
    DISCARDED_FAMILY_MARKERS,
    NAMED_IN_SPEC,
    RAW_MODELS,
)

pytestmark = pytest.mark.unit


def _offerings() -> tuple[ModelOffering, ...]:
    return tuple(
        ModelOffering(
            model_id=entry["name"].removeprefix("models/"), display_name=entry["displayName"]
        )
        for entry in RAW_MODELS
    )


# --- Curation ----------------------------------------------------------------


def test_the_fixture_itself_is_internally_consistent() -> None:
    """A guard on the fixture, not on the code under test: every discarded
    entry actually carries one of the markers the curation rules key on, or
    the tests below would be proving something about a fixture that does not
    represent what it claims to."""
    kept = {offering.model_id for offering in curate(_offerings())}
    discarded = {offering.model_id for offering in _offerings()} - kept
    assert discarded
    for model_id in discarded:
        assert any(marker in model_id for marker in DISCARDED_FAMILY_MARKERS), model_id


def test_curation_keeps_every_model_the_specification_names() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    for model_id in NAMED_IN_SPEC:
        assert model_id in kept


def test_curation_keeps_the_latest_aliases() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert "gemini-pro-latest" in kept
    assert "gemini-flash-latest" in kept


def test_curation_discards_every_image_model() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert not any("imagen" in model_id for model_id in kept)


def test_curation_discards_every_audio_and_speech_model() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert not any("tts" in model_id or "audio" in model_id for model_id in kept)


def test_curation_discards_every_robotics_model() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert not any("robotics" in model_id for model_id in kept)


def test_curation_discards_every_music_model() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert "lyria-002" not in kept


def test_curation_discards_every_embedding_model() -> None:
    kept = {offering.model_id for offering in curate(_offerings())}
    assert not any("embed" in model_id for model_id in kept)


def test_curation_never_uses_tool_support_as_a_criterion() -> None:
    """A text model the registry has no `supports_tools` opinion about yet
    stays in the list — that capability is established by verification, not by
    the listing. `ModelOffering` carries no such field at all, which is the
    stronger guarantee: there is no field curation *could* read to exclude on."""
    assert not hasattr(ModelOffering, "supports_tools")
    kept = {offering.model_id for offering in curate(_offerings())}
    assert "gemini-3.7-flash" in kept


def test_curated_models_keep_the_display_name_the_endpoint_returned() -> None:
    kept = {offering.model_id: offering.display_name for offering in curate(_offerings())}
    assert kept["gemini-3.7-flash"] == "Gemini 3.7 Flash"


# --- Cache ---------------------------------------------------------------------


async def test_two_reads_within_the_time_to_live_call_the_endpoint_once() -> None:
    calls = 0

    async def fetch() -> tuple[ModelOffering, ...]:
        nonlocal calls
        calls += 1
        return _offerings()

    cache = ModelCatalogueCache()
    await cache.get("google_gemini", fetch=fetch)
    await cache.get("google_gemini", fetch=fetch)

    assert calls == 1


async def test_a_refresh_ignores_the_cache_and_calls_exactly_once_more() -> None:
    calls = 0

    async def fetch() -> tuple[ModelOffering, ...]:
        nonlocal calls
        calls += 1
        return _offerings()

    cache = ModelCatalogueCache()
    await cache.get("google_gemini", fetch=fetch)
    await cache.get("google_gemini", fetch=fetch, refresh=True)

    assert calls == 2


async def test_an_expired_entry_is_fetched_again() -> None:
    calls = 0
    clock = [0.0]

    async def fetch() -> tuple[ModelOffering, ...]:
        nonlocal calls
        calls += 1
        return _offerings()

    cache = ModelCatalogueCache(ttl_seconds=10.0, clock=lambda: clock[0])
    await cache.get("google_gemini", fetch=fetch)
    clock[0] = 11.0
    await cache.get("google_gemini", fetch=fetch)

    assert calls == 2


async def test_different_providers_are_cached_separately() -> None:
    calls: dict[str, int] = {}

    def fetcher(provider_id: str) -> object:
        async def fetch() -> tuple[ModelOffering, ...]:
            calls[provider_id] = calls.get(provider_id, 0) + 1
            return _offerings()

        return fetch

    cache = ModelCatalogueCache()
    await cache.get("google_gemini", fetch=fetcher("google_gemini"))
    await cache.get("anthropic", fetch=fetcher("anthropic"))

    assert calls == {"google_gemini": 1, "anthropic": 1}


# --- Fallback --------------------------------------------------------------------


async def test_an_endpoint_error_falls_back_to_the_static_list_labelled_as_such() -> None:
    from core.llm.catalogue import ListingUnavailable, listing_for

    async def broken() -> tuple[ModelOffering, ...]:
        raise ListingUnavailable("the endpoint answered with an error")

    result = await listing_for(
        "google_gemini", fetch=broken, static=(ModelOffering("gemini-pro-latest", "Gemini Pro"),)
    )

    assert result.source == "static"
    assert result.reason != ""
    assert [offering.model_id for offering in result.models] == ["gemini-pro-latest"]


async def test_an_empty_listing_after_curation_is_treated_as_unavailable() -> None:
    from core.llm.catalogue import listing_for

    async def only_images() -> tuple[ModelOffering, ...]:
        return (ModelOffering("imagen-4.0-generate-001", "Imagen 4.0"),)

    result = await listing_for(
        "google_gemini",
        fetch=only_images,
        static=(ModelOffering("gemini-pro-latest", "Gemini Pro"),),
    )

    assert result.source == "static"
    assert result.reason != ""


async def test_a_provider_that_declares_no_listing_support_reaches_the_same_fallback() -> None:
    """The absence of listing support must be indistinguishable, to whoever
    consumes this, from a listing call that failed — both land on the
    identical, honestly labelled fallback."""
    from core.llm.catalogue import ListingUnavailable, listing_for

    async def declares_no_support() -> tuple[ModelOffering, ...]:
        raise ListingUnavailable("this provider has no model-listing endpoint")

    result_a = await listing_for(
        "ollama", fetch=declares_no_support, static=(ModelOffering("llama4:70b", "Llama 4 70B"),)
    )

    async def call_failed() -> tuple[ModelOffering, ...]:
        raise ListingUnavailable("the endpoint timed out")

    result_b = await listing_for(
        "google_gemini",
        fetch=call_failed,
        static=(ModelOffering("gemini-pro-latest", "Gemini Pro"),),
    )

    assert result_a.source == result_b.source == "static"


async def test_a_working_listing_is_curated_and_labelled_as_the_endpoint() -> None:
    from core.llm.catalogue import listing_for

    async def fetch() -> tuple[ModelOffering, ...]:
        return _offerings()

    result = await listing_for("google_gemini", fetch=fetch, static=())

    assert result.source == "endpoint"
    assert result.reason == ""
    kept = {offering.model_id for offering in result.models}
    assert "gemini-3.7-flash" in kept
    assert not any("imagen" in model_id for model_id in kept)
