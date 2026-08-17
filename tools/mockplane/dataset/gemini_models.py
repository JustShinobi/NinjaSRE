"""The Gemini models this deployment's listing endpoint has been observed to serve.

A representative snapshot built to exercise the curation and cache logic
``core.llm.catalogue`` applies to whatever a provider's own listing endpoint
returns — not a byte-for-byte capture re-taken during this implementation
session, and the docstring says so rather than implying otherwise. It carries
every model this feature's own specification names by identifier (three
generations the onboarding list had never heard of, and the ``-latest``
aliases that keep a catalogue pointed at the current one without pinning a
generation that will retire), plus enough entries from each family the
curation discards — image, audio and speech, robotics, music, embedding — that
the discarding rules have something real to discard rather than an empty set
that would pass by having nothing to fail on.

Read by the curation unit tests and by the mock data plane's model-listing
endpoint, so the two never file two different answers to "what did the
endpoint say it serves".

Shaped like the raw document the vendor's own listing endpoint returns: one
entry per model, a ``name`` carrying the ``models/`` prefix the wire uses, the
``displayName`` the API assigns, and the generation methods it advertises. A
provider implementation reads this shape and is the one place that translates
it into the neutral ``ModelOffering`` the rest of the platform uses.
"""

from __future__ import annotations

from typing import Final, TypedDict


class RawGeminiModel(TypedDict):
    """One entry of the vendor's own `GET /v1beta/models` document."""

    name: str
    displayName: str
    supportedGenerationMethods: list[str]


def _text(model_id: str, display_name: str) -> RawGeminiModel:
    """Return a generative-text entry: the shape curation is meant to keep."""
    return {
        "name": f"models/{model_id}",
        "displayName": display_name,
        "supportedGenerationMethods": ["generateContent", "countTokens"],
    }


#: The 37 models this deployment's endpoint listed with `generateContent`
#: among their supported generation methods — the same count the specification
#: cites. 26 are generative text models the curation must keep; 11 belong to
#: the five families (image, audio/speech, robotics, music, embedding) the
#: curation must discard.
RAW_MODELS: Final[tuple[RawGeminiModel, ...]] = (
    # --- Kept: generative text, the aliases first -----------------------------
    _text("gemini-pro-latest", "Gemini Pro (Latest)"),
    _text("gemini-flash-latest", "Gemini Flash (Latest)"),
    _text("gemini-flash-lite-latest", "Gemini Flash-Lite (Latest)"),
    _text("gemini-1.5-pro", "Gemini 1.5 Pro"),
    _text("gemini-1.5-flash", "Gemini 1.5 Flash"),
    _text("gemini-1.5-flash-8b", "Gemini 1.5 Flash-8B"),
    _text("gemini-2.0-pro-exp", "Gemini 2.0 Pro Experimental"),
    _text("gemini-2.0-flash", "Gemini 2.0 Flash"),
    _text("gemini-2.0-flash-lite", "Gemini 2.0 Flash-Lite"),
    _text("gemini-2.0-flash-exp", "Gemini 2.0 Flash Experimental"),
    _text("gemini-2.5-pro", "Gemini 2.5 Pro"),
    _text("gemini-2.5-flash", "Gemini 2.5 Flash"),
    _text("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    _text("gemini-2.5-pro-preview-05-06", "Gemini 2.5 Pro Preview 05-06"),
    _text("gemini-2.5-flash-preview-05-20", "Gemini 2.5 Flash Preview 05-20"),
    _text("gemini-3.0-pro", "Gemini 3.0 Pro"),
    _text("gemini-3.0-flash", "Gemini 3.0 Flash"),
    _text("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview"),
    _text("gemini-3.1-flash", "Gemini 3.1 Flash"),
    _text("gemini-3.5-pro", "Gemini 3.5 Pro"),
    _text("gemini-3.5-flash", "Gemini 3.5 Flash"),
    _text("gemini-3.6-pro", "Gemini 3.6 Pro"),
    _text("gemini-3.6-flash", "Gemini 3.6 Flash"),
    _text("gemini-3.7-pro", "Gemini 3.7 Pro"),
    _text("gemini-3.7-flash", "Gemini 3.7 Flash"),
    _text("gemini-3.7-flash-lite", "Gemini 3.7 Flash-Lite"),
    # --- Discarded: image -------------------------------------------------------
    _text("imagen-3.0-generate-002", "Imagen 3.0 Generate"),
    _text("imagen-4.0-generate-001", "Imagen 4.0 Generate"),
    _text("imagen-4.0-ultra-generate-001", "Imagen 4.0 Ultra Generate"),
    # --- Discarded: audio and speech --------------------------------------------
    _text("gemini-2.5-flash-preview-tts", "Gemini 2.5 Flash Preview TTS"),
    _text("gemini-2.5-pro-preview-tts", "Gemini 2.5 Pro Preview TTS"),
    _text(
        "gemini-2.5-flash-native-audio-preview-09-2025",
        "Gemini 2.5 Flash Native Audio Preview",
    ),
    # --- Discarded: robotics -----------------------------------------------------
    _text("gemini-robotics-er-1.5-preview", "Gemini Robotics-ER 1.5 Preview"),
    # --- Discarded: music ---------------------------------------------------------
    _text("lyria-002", "Lyria 2"),
    # --- Discarded: embedding -------------------------------------------------------
    _text("gemini-embedding-001", "Gemini Embedding"),
    _text("gemini-embedding-exp-03-07", "Gemini Embedding Experimental 03-07"),
    _text("text-embedding-004", "Text Embedding 004"),
)

assert len(RAW_MODELS) == 37, "the specification cites 37 models observed with generateContent"

#: The identifiers this feature's specification names by name, and which the
#: curation must keep. Cross-checked by the unit tests against `RAW_MODELS`
#: rather than repeated as a second literal list.
NAMED_IN_SPEC: Final[tuple[str, ...]] = (
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-pro-latest",
    "gemini-flash-latest",
)

#: The substrings a discarded entry's identifier carries, matched against the
#: 11 entries above — used by the curation tests to assert the fixture itself
#: is internally consistent before it is asked to prove anything about the
#: code under test.
DISCARDED_FAMILY_MARKERS: Final[tuple[str, ...]] = (
    "imagen",
    "tts",
    "native-audio",
    "robotics",
    "lyria",
    "embedding",
)


__all__ = [
    "DISCARDED_FAMILY_MARKERS",
    "NAMED_IN_SPEC",
    "RAW_MODELS",
    "RawGeminiModel",
]
