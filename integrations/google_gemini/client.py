"""Gemini, reached through the credential proxy.

One method. This client exists so a stored key can be *verified* and so the
provider is an integration like every other — not to carry inference traffic,
which the model layer already handles through its own adapters.

The distinction matters: an operator configuring a provider needs to know the
key works before the first investigation depends on it, and the only honest way
to answer that is to use the key.
"""

from __future__ import annotations

from typing import Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.google_gemini.schema import DEFAULT_HOST, INTEGRATION

#: The cheapest read the API offers that still requires the key: it lists the
#: models this key may use, which is also the question an operator has after
#: storing one.
LIST_MODELS_PATH: Final = "/v1beta/models"


class GeminiClient(IntegrationClient):
    """Google Gemini, reached through the credential proxy."""

    integration = INTEGRATION

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        base_url: str = "",
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url or f"https://{DEFAULT_HOST}",
            retry=retry,
        )

    async def ping(self) -> ClientResponse:
        """Make the cheapest authenticated call the API offers.

        Listing models proves the key authenticates and spends no inference
        quota, which is what a verification owes an operator.
        """
        return await self.get(LIST_MODELS_PATH)


__all__ = ["LIST_MODELS_PATH", "GeminiClient"]
