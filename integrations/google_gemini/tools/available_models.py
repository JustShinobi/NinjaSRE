"""Which models this deployment's key may actually use.

The question an operator has immediately after storing a provider key, and the
one a failing investigation raises: the deployment is configured for a model,
and the key may not be allowed to call it. Those two facts live in different
places and only the provider can reconcile them.

Read-only, and it spends no inference quota — listing models is the cheapest
call the API offers that still requires the key.
"""

from __future__ import annotations

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.google_gemini.client import GeminiClient
from integrations.google_gemini.schema import INTEGRATION

TOOL_NAME = "google_gemini_available_models"

_USE_CASES = (
    "checking that a stored provider key can call the model this deployment is configured for",
    "explaining a provider refusal that names a model rather than the key",
)

_ANTI_EXAMPLES = (
    "running an inference, which goes through the model layer rather than here",
    "choosing a model for a task, which is a configuration decision rather than a reading",
)


@tool(
    name=TOOL_NAME,
    display_name="Gemini available models",
    description=(
        "List the models this deployment's Google Gemini key is allowed to call. The "
        "question an operator has after storing a key, and the one a provider refusal "
        "naming a model raises. Spends no inference quota."
    ),
    domain="model_provider",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CONFIGURATION,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("model_provider", "gemini", "google", "credentials"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def google_gemini_available_models() -> CapabilityResult:
    """Return the models this deployment's key may call."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(GeminiClient, capability=TOOL_NAME)
    try:
        answer = (await client.ping()).json()
    except IntegrationError as failed:
        return vendor_failure(TOOL_NAME, failed)

    models = [
        str(entry.get("name", ""))
        for entry in (answer.get("models") or [])
        if isinstance(entry, dict)
    ]
    return CapabilityResult.ok(
        TOOL_NAME,
        value={"models": models, "count": len(models)},
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CONFIGURATION,
                summary=f"the stored key may call {len(models)} model(s)",
                reference=f"{INTEGRATION}:models",
            ),
        ),
    )


__all__ = ["TOOL_NAME", "google_gemini_available_models"]
