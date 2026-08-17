"""What a provider's own endpoint says it currently serves.

The static registry (``core.llm.registry``) is this platform's best reading of
a vendor's documentation: pricing, context windows, the odd hand-maintained
list of model names. That last part is the one that rots — a vendor ships a
model and the registry finds out whenever somebody notices. This package is
the other source: a provider is asked directly, the answer is curated down to
models that can actually run an investigation, and cached so that opening a
screen three times does not call the vendor three times.

**Curation never reads tool-calling support.** Whether a model can call a tool
is established by verification — a real, forced call — never by a name pattern
or a flag on the listing. What curation excludes is *kind*: an image generator,
a text-to-speech model, a robotics model, a music model, an embedding model —
none of them can run an investigation regardless of what they say about tools.

**The absence of a listing is a fact a provider declares, not an exception a
caller catches by accident.** A provider with nothing to say about "what else
do you serve" and a provider whose endpoint just failed are, to every caller
here, the identical case: both raise :class:`ListingUnavailable`, and both fall
through to the same labelled fallback. That is the same provider-neutrality
this platform holds everywhere else, applied to a listing rather than to an
adapter — no provider gets a special branch on the surfaces that consume this.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.llm.credentials import ProviderCredentials
from core.llm.redaction import external_error_summary

#: Substrings that mark a model as belonging to one of the five families this
#: platform cannot run an investigation on, matched against the lower-cased
#: model identifier. Not a statement about quality — an image generator is not
#: a worse investigator, it is not an investigator, because it cannot call the
#: tools an investigation is made of.
_EXCLUDED_FAMILY_MARKERS: tuple[str, ...] = (
    "image",  # image generation, including the "imagen" family
    "tts",  # text-to-speech
    "audio",  # speech and native-audio variants
    "robotics",
    "lyria",  # music generation
    "embed",  # embedding models, including "embedding" and "text-embedding"
)


@dataclass(frozen=True, slots=True)
class ModelOffering:
    """One model a provider's endpoint says it currently serves."""

    model_id: str
    display_name: str


class ListingUnavailable(Exception):
    """This provider's listing could not be asked, or has nothing to ask.

    Raised alike whether the provider has no listing implementation at all or
    a live call to one that exists failed — the two are indistinguishable to
    whoever consumes this, which is what lets both fall into the identical,
    honestly labelled fallback.
    """


@runtime_checkable
class ModelCatalogue(Protocol):
    """The port: what models does this provider's endpoint currently serve."""

    async def list_models(self, credentials: ProviderCredentials) -> tuple[ModelOffering, ...]:
        """Return the models the endpoint currently serves, uncurated.

        Raises:
            ListingUnavailable: the endpoint could not answer, or this
                provider declares that it cannot be asked.
        """


def curate(offerings: Sequence[ModelOffering]) -> tuple[ModelOffering, ...]:
    """Return ``offerings`` narrowed to models this platform can drive an investigation on.

    Order is preserved — the caller's own order is usually the vendor's, which
    is worth keeping rather than re-sorting into an order nobody asked for.
    """
    return tuple(
        offering
        for offering in offerings
        if not any(marker in offering.model_id.lower() for marker in _EXCLUDED_FAMILY_MARKERS)
    )


@dataclass(frozen=True, slots=True)
class ModelListing:
    """A curated list of models, and where it came from."""

    models: tuple[ModelOffering, ...]
    #: ``"endpoint"`` when the provider's own listing answered, ``"static"``
    #: when this is the registry's fallback list.
    source: str
    #: Why the fallback was used. Empty when ``source == "endpoint"``.
    reason: str = ""


async def listing_for(
    provider_id: str,
    *,
    fetch: Callable[[], Awaitable[tuple[ModelOffering, ...]]],
    static: Sequence[ModelOffering],
) -> ModelListing:
    """Return the curated listing for ``provider_id``, falling back honestly.

    ``fetch`` is whatever asked the endpoint — already resolved to this
    provider's credentials, already curated or not (curation is applied here
    either way, so a caller cannot forget it). A listing that comes back empty
    after curation is treated exactly like one that failed to arrive: neither
    is a usable answer to "what can this deployment offer", and both fall to
    the same static list, labelled.
    """
    try:
        raw = await fetch()
    except ListingUnavailable as error:
        # The redacted summary only, never the exception's own message: a
        # listing implementation's failure text is written for whoever holds
        # the credential it just used, the same reason `core.llm.redaction`
        # exists for an invocation failure, and this reason field is read by
        # anyone who may read configuration, not only the operator who set the
        # key.
        return ModelListing(
            models=curate(tuple(static)),
            source="static",
            reason=f"{provider_id}'s listing could not be used: {external_error_summary(error)}",
        )

    curated = curate(raw)
    if not curated:
        return ModelListing(
            models=curate(tuple(static)),
            source="static",
            reason=(
                f"{provider_id}'s endpoint answered, but nothing it listed was a model of "
                f"text this platform can drive an investigation on"
            ),
        )
    return ModelListing(models=curated, source="endpoint")


_CATALOGUES: dict[str, ModelCatalogue] = {}


def register_catalogue(provider_id: str, catalogue: ModelCatalogue) -> None:
    """Register or replace the listing implementation for one provider."""
    _CATALOGUES[provider_id] = catalogue


def catalogue_for(provider_id: str) -> ModelCatalogue | None:
    """Return the listing implementation for ``provider_id``, or ``None``.

    ``None`` rather than an exception: a provider with no implementation
    registered is exactly the case :class:`ListingUnavailable` exists to make
    indistinguishable from a failed call, and the caller that turns this into
    that exception is the one place that decision belongs.
    """
    return _CATALOGUES.get(provider_id)


__all__ = [
    "ListingUnavailable",
    "ModelCatalogue",
    "ModelListing",
    "ModelOffering",
    "catalogue_for",
    "curate",
    "listing_for",
    "register_catalogue",
]


def _register_shipped_catalogues() -> None:
    """Register every implementation this build ships.

    Imported last, and only for its side effect: each module registers itself
    rather than being listed twice, here and in its own file — the same reason
    ``core.llm.providers`` builds its adapter dictionary from imports rather
    than from a second registry a tenth provider could forget to update.
    """
    from core.llm.catalogue import gemini

    gemini.register()


_register_shipped_catalogues()
