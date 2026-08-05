"""Azure OpenAI: the same wire, addressed differently.

Three differences from OpenAI, and all three have cost somebody a night:

- The URL names a **deployment**, not a model. An operator's deployment can be
  called anything, so the descriptor's model is what NinjaSRE reasons about and
  the deployment is what goes on the wire.
- The API **version** is pinned per request, and features appear and disappear
  between versions. A pin the operator sets beats a default that drifts.
- Authentication is a separate key against a separate endpoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from config.constants.llm import PROVIDER_AZURE_OPENAI
from core.llm.cache import CachePlan
from core.llm.credentials import ProviderCredentials
from core.llm.providers.openai_compat import OpenAiCompatibleAdapter
from core.llm.registry import ModelDescriptor
from core.llm.types import InvokeRequest


class AzureOpenAiAdapter(OpenAiCompatibleAdapter):
    """OpenAI's wire, reached through an Azure deployment."""

    provider_identifier = PROVIDER_AZURE_OPENAI

    def build_payload(
        self,
        request: InvokeRequest,
        descriptor: ModelDescriptor,
        cache: CachePlan,
    ) -> dict[str, Any]:
        """Return the body with the deployment in the model slot.

        The Azure client takes the deployment where OpenAI's takes the model,
        and a descriptor without one falls back to the model name — which is the
        convention when an operator names the deployment after the model.
        """
        payload = super().build_payload(request, descriptor, cache)
        payload["model"] = descriptor.deployment_id or descriptor.model_id
        return payload

    def routing(
        self, credentials: ProviderCredentials, descriptor: ModelDescriptor
    ) -> Mapping[str, str]:
        """Return the deployment and API version, which are not body fields."""
        routing: dict[str, str] = {}
        deployment = credentials.get("deployment") or descriptor.deployment_id
        if deployment:
            routing["deployment"] = deployment
        api_version = credentials.get("api_version")
        if api_version:
            routing["api_version"] = api_version
        return routing


__all__ = ["AzureOpenAiAdapter"]
