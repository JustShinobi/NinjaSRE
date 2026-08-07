"""The credential proxy as a deployable service: composition, transport, entry point.

``platform/credentials/proxy/`` is the proxy — resolution, injection, signing,
the allow-list, the audit trail. None of it can be composed there, because
filling the injection-rule registry means reading every installed integration's
declaration and ``platform/`` is tier 3. This package is the tier-1 half: it
gathers the declarations, supplies the thing that puts bytes on the wire, and
serves the result.

The dev profile mounts ``ProxyApp`` in the application's own process and never
uses this entry point. Same object, same rules, same audit — which is what makes
"identical behaviour in every profile" a fact about the object graph rather than
a claim about two implementations.
"""

from __future__ import annotations

from gateway.proxy.composition import build_proxy_app, build_proxy_engine
from gateway.proxy.sender import HttpOutboundSender, trust_context

__all__ = [
    "HttpOutboundSender",
    "build_proxy_app",
    "build_proxy_engine",
    "trust_context",
]
