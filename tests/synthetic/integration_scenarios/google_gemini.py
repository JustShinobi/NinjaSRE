"""Gemini, end to end: capability, client, proxy, injection, vendor.

The seventh parity artefact, and for this integration the one that matters most.
Everything else can look finished while the key still never reaches the wire —
which is exactly the defect this integration exists to close: a provider key
that a console could store and nothing could read.

So this drives the whole path, including the credential proxy with this
integration's own injection rule. A key that stopped being injected, or started
being injected into the query string, fails here.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

#: Not a real credential. The suite asserts that none of these values reaches a
#: client, a result, or a trace.
CREDENTIAL: Final[dict[str, str]] = {
    "api_key": "ninjasre-scenario-key-000000",
}


AVAILABLE_MODELS: Final = IntegrationScenario(
    key="google-gemini-available-models",
    integration="google_gemini",
    capability="google_gemini_available_models",
    arguments={},
    responses=(
        json_response(
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-pro",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="may call 2 model(s)",
    expected_paths=("/v1beta/models",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (AVAILABLE_MODELS,)

__all__ = ["AVAILABLE_MODELS", "CREDENTIAL", "SCENARIOS"]
