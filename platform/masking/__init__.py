"""Reversible replacement of infrastructure identifiers at the external-LLM boundary.

    from platform.masking import MaskingContext, MaskingLLMClient, MaskingPolicy

    context = MaskingContext(policy=MaskingPolicy.from_level("standard"))
    client = MaskingLLMClient(inner=provider_client, context=context)

Everything above that wrapper deals in real pod names and cluster names; only
what crosses to the provider sees a token. ``platform.masking.llm`` explains why
the boundary is a decorator rather than a change inside ``core/llm/``.
"""

from __future__ import annotations

from platform.masking.apply import mask, unmask
from platform.masking.context import MaskingContext
from platform.masking.detectors import DetectedIdentifier, Detector, IdentifierKind, detect
from platform.masking.llm import MaskingLLMClient
from platform.masking.mapping import MaskMapping
from platform.masking.policy import (
    DEFAULT_POLICY,
    CustomPattern,
    CustomPatternError,
    MaskingLevel,
    MaskingPolicy,
)

__all__ = [
    "DEFAULT_POLICY",
    "CustomPattern",
    "CustomPatternError",
    "DetectedIdentifier",
    "Detector",
    "IdentifierKind",
    "MaskMapping",
    "MaskingContext",
    "MaskingLLMClient",
    "MaskingLevel",
    "MaskingPolicy",
    "detect",
    "mask",
    "unmask",
]
