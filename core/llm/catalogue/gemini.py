"""google_gemini's own answer to "what models do you currently serve".

The first implementation of the listing port — provider-neutral by contract,
one implementation per provider, no vendor branch on a surface. A plain REST
call rather than the SDK client the invocation path uses — this is a single,
cheap `GET`, and pulling in the generative-language client for one endpoint
would be a heavier dependency than the call it makes.
"""

from __future__ import annotations

from typing import Any

import httpx

from config.constants.llm import (
    GOOGLE_GENERATIVE_LANGUAGE_MODELS_URL,
    MODEL_LISTING_FETCH_TIMEOUT_SECONDS,
    PROVIDER_GOOGLE_GEMINI,
)
from core.llm.catalogue import ListingUnavailable, ModelOffering
from core.llm.credentials import ProviderCredentials

#: The generation method a model must advertise to be worth offering at all —
#: everything downstream of the listing assumes a chat-shaped call.
_REQUIRED_METHOD = "generateContent"


class GeminiModelCatalogue:
    """Lists the models this deployment's Gemini key can currently reach."""

    async def list_models(self, credentials: ProviderCredentials) -> tuple[ModelOffering, ...]:
        """Return every model the endpoint reports with `generateContent`, uncurated.

        Raises:
            ListingUnavailable: no credential to ask with, the endpoint could
                not be reached, or it answered with something this cannot read.
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ListingUnavailable("no credential is stored for google_gemini")

        try:
            # The key travels as a header, never as a query parameter: a query
            # string is what an access log, a proxy log, or a browser history
            # entry captures whole, and Google's own API accepts either.
            async with httpx.AsyncClient(timeout=MODEL_LISTING_FETCH_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    GOOGLE_GENERATIVE_LANGUAGE_MODELS_URL,
                    headers={"x-goog-api-key": api_key},
                )
        except httpx.HTTPError as error:
            raise ListingUnavailable(
                f"google_gemini's listing endpoint could not be reached: {error}"
            ) from error

        if response.status_code != 200:
            raise ListingUnavailable(
                f"google_gemini's listing endpoint answered {response.status_code}"
            )

        try:
            document = response.json()
        except ValueError as error:
            raise ListingUnavailable(
                "google_gemini's listing endpoint answered with a document that is not JSON"
            ) from error

        return _offerings_of(document)


def _offerings_of(document: Any) -> tuple[ModelOffering, ...]:
    """Return the offerings a raw `GET .../models` document describes."""
    raw = document.get("models") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        raise ListingUnavailable(
            "google_gemini's listing endpoint answered with no models field to read"
        )

    offerings: list[ModelOffering] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        methods = entry.get("supportedGenerationMethods")
        if not isinstance(methods, list) or _REQUIRED_METHOD not in methods:
            continue
        model_id = str(entry.get("name") or "").removeprefix("models/")
        if not model_id:
            continue
        display_name = str(entry.get("displayName") or model_id)
        offerings.append(ModelOffering(model_id=model_id, display_name=display_name))
    return tuple(offerings)


def register() -> None:
    """Register this implementation for `google_gemini` on the shared catalogue registry."""
    from core.llm.catalogue import register_catalogue

    register_catalogue(PROVIDER_GOOGLE_GEMINI, GeminiModelCatalogue())


__all__ = ["GeminiModelCatalogue", "register"]
