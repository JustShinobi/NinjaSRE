"""The two provider routes the console's Models & providers screen depends on.

``POST /{provider_id}/verify`` carries the checks the preflight ran, one entry
per check, so a screen mirrors them instead of collapsing to a boolean.
``GET /{provider_id}/models`` serves the curated listing a model selector
reads, and says whether it came from the endpoint or from the static
fallback. Source-level, the way this directory checks a payload shape without
a live call — the functional behaviour these fields carry is exercised
end-to-end in ``tests/unit/gateway/http/test_onboarding_routes.py``.
"""

from __future__ import annotations

import pytest

from core.llm.catalogue import ModelListing, ModelOffering, curate, listing_for
from gateway.http.routes.providers import (
    CheckResultView,
    ModelListingView,
    ModelOfferingView,
    ProviderVerificationView,
    list_models,
    verify_provider,
)

pytestmark = pytest.mark.contract


def test_the_verification_view_declares_a_checks_field_of_check_views() -> None:
    fields = ProviderVerificationView.model_fields
    assert "checks" in fields, (
        "ProviderVerificationView has no checks field; a screen mirroring the "
        "preflight has nothing to mirror it from"
    )


def test_the_check_view_carries_name_status_detail_and_duration() -> None:
    fields = CheckResultView.model_fields
    for name in ("name", "status", "detail", "duration_ms"):
        assert name in fields, f"CheckResultView has no {name!r} field"


def test_the_listing_view_says_where_the_models_came_from() -> None:
    fields = ModelListingView.model_fields
    assert "source" in fields
    assert "reason" in fields
    assert "models" in fields
    assert ModelOfferingView.model_fields.keys() >= {"model_id", "display_name"}


def test_the_verify_route_reads_checks_from_the_verdict_rather_than_recomputing_them() -> None:
    """Source-level: the route function's body names ``verdict.checks``, so a
    verdict without any never gets checks invented for it at this layer."""
    import inspect

    source = inspect.getsource(verify_provider)
    assert "verdict.checks" in source


def test_the_models_route_is_wired_to_the_curated_listing_helper() -> None:
    import inspect

    source = inspect.getsource(list_models)
    assert "_listing" in source


# --- The curation + fallback contract the route relies on, exercised directly --


async def test_a_curated_listing_excludes_every_declared_family() -> None:
    async def fetch() -> tuple[ModelOffering, ...]:
        return (
            ModelOffering("gemini-3.7-flash", "Gemini 3.7 Flash"),
            ModelOffering("imagen-4.0-generate-001", "Imagen 4.0"),
        )

    listing = await listing_for("google_gemini", fetch=fetch, static=())

    assert isinstance(listing, ModelListing)
    assert listing.source == "endpoint"
    model_ids = {offering.model_id for offering in listing.models}
    assert model_ids == {"gemini-3.7-flash"}


def test_curate_is_a_pure_function_of_its_input() -> None:
    offerings = (ModelOffering("gemini-pro-latest", "Gemini Pro"),)
    assert curate(offerings) == curate(offerings)
