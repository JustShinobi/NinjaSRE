"""What makes two client requests the same client.

Its own module because it is worth reading on its own. Every input that changes
a client's behaviour has to be in this key. One that is missing does not fail
loudly: it hands a caller a client configured for something else, and the
symptom appears somewhere unrelated — a request going to the wrong deployment,
or a transport the operator switched away from still serving traffic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientCacheKey:
    """Identifies one client configuration.

    Frozen and hashable so it can be a dictionary key, and complete so it is a
    correct one. ``role`` is included even though it usually implies the rest:
    two roles pointed at the same model still get their own client, which keeps
    a per-role change from silently applying to every other role.
    """

    role: str
    provider_id: str
    model_id: str
    transport: str
    #: An operator's endpoint override. Two clients differing only in base URL
    #: are different clients — this is what separates a local Ollama from a
    #: remote vLLM serving the same model name.
    base_url: str = ""
    #: Azure's deployment, Bedrock's inference profile.
    deployment_id: str = ""

    def replace_transport(self, transport: str) -> ClientCacheKey:
        """Return the same key against a different transport."""
        return ClientCacheKey(
            role=self.role,
            provider_id=self.provider_id,
            model_id=self.model_id,
            transport=transport,
            base_url=self.base_url,
            deployment_id=self.deployment_id,
        )


__all__ = ["ClientCacheKey"]
