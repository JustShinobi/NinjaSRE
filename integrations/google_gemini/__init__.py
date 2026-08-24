"""Google Gemini, reached the way every other authenticated call is reached.

A provider key could be stored and never read: the vault held it, the vault's
``reveal`` belongs to the credential proxy alone, and the proxy had no rule for
any language-model provider. So the key went in and stopped there while the
model client read an environment variable — the one place Article IV says a
credential must never be, holding the most sensitive credential in the system.

Declaring the provider as an integration closes that. The key works because it
was stored, rather than working because it was also exported.
"""

from __future__ import annotations

from typing import Final

from integrations._catalogue.entry import IntegrationCategory, IntegrationProfile
from integrations.google_gemini.client import GeminiClient
from integrations.google_gemini.schema import (
    DEFAULT_HOST,
    HOSTS,
    INTEGRATION,
    REGIONS,
    RULE,
    SCHEMA,
)
from integrations.google_gemini.verifier import PERMISSIONS, GeminiVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

GEMINI: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=RULE,
    verifier=GeminiVerifier(),
    client_class=GeminiClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The vendor SDK loads its key from a constructor argument or the environment, "
        "which is the behaviour Article IV forbids and the one thing about such a library "
        "that is never configurable away. This client makes one read — the model listing — "
        "so a direct client on the proxy transport costs less than the adaptation would "
        "and holds nothing. Inference itself goes through the model layer's own adapters."
    ),
)

DESCRIPTOR: Final = GEMINI

PROFILE: Final = IntegrationProfile(
    integration=INTEGRATION,
    display_name="Google Gemini",
    category=IntegrationCategory.MODEL_PROVIDER,
    summary=(
        "Google Gemini, declared so a provider key stored in the vault is reachable "
        "through the credential proxy rather than only through the process environment."
    ),
    regions=REGIONS,
    permissions=PERMISSIONS,
    where_to_get_it=(
        "Create an API key in Google AI Studio, in the project you want billed for the "
        "calls this deployment makes."
    ),
)

__all__ = [
    "DEFAULT_HOST",
    "DESCRIPTOR",
    "GEMINI",
    "HOSTS",
    "INTEGRATION",
    "PERMISSIONS",
    "PROFILE",
    "REGIONS",
    "RULE",
    "SCHEMA",
    "GeminiClient",
    "GeminiVerifier",
]
