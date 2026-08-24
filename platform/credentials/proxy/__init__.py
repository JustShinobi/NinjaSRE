"""The credential proxy: the only component in NinjaSRE that reads a secret.

Constitution Article IV says the agent never holds a credential. This package is
the mechanism that makes that structurally true rather than aspirationally true.
A capability builds a request carrying a tenant, a team, and an integration
handle — all safe in a prompt, a trace, or a log line — and the proxy resolves
the handle against the encrypted vault and injects the real secret at the
network edge.

Read ``engine.py`` first. It is the sequence, and every other module here is one
step of it:

===================  =========================================================
``model``            the request before and after injection, and the send port
``resolution``       handle plus tenant plus team to a credential — the only
                     caller of ``CredentialStore.reveal`` in the whole platform
``injection``        the declared ways a secret enters a request, per vendor
``egress``           the per-integration allow-list, enforced before the vault
``signing/``         schemes that need the key at construction time — SigV4 and
                     its relatives
``refresh``          short-lived credentials, and the single expiry retry
``rate_limit``       per-tenant ceilings, refused rather than queued
``audit``            one record per resolution, never carrying the value
``app``              the ASGI mount, in-process in ``dev`` and served otherwise
``errors``           why a call was refused, classified for the agent
===================  =========================================================

**There is no bypass** (FR-010). No flag, no environment variable, no degraded
mode. A deployment without a working proxy is a deployment where authenticated
calls fail, loudly, with an error naming the integration — because a fallback is
the switch that gets flipped during an outage and never flipped back.
"""

from __future__ import annotations

from platform.credentials.proxy.app import ProxyApp, create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor, ResolutionRecord
from platform.credentials.proxy.engine import ProxyEngine, ProxyHealth
from platform.credentials.proxy.errors import (
    CredentialExpired,
    CredentialFieldsMissing,
    CredentialUnavailable,
    CredentialUnreadable,
    CredentialWouldCrossInClear,
    EgressDenied,
    IntegrationNotDeclared,
    MalformedProxyRequest,
    ProxyError,
    ProxyErrorReason,
    RefreshFailed,
    TenantRateLimited,
    UpstreamUnreachable,
)
from platform.credentials.proxy.injection import (
    BasicAuthInjection,
    BearerTokenInjection,
    BodyFieldInjection,
    HeaderInjection,
    Injection,
    InjectionRule,
    InjectionRuleRegistry,
    PathSegmentInjection,
    QueryParameterInjection,
    RequestSigner,
    SignatureInjection,
)
from platform.credentials.proxy.model import (
    OutboundRequest,
    OutboundResponse,
    OutboundSender,
    ProxyRequest,
)
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.credentials.proxy.refresh import (
    CredentialRefresher,
    RefreshedCredential,
    needs_refresh,
)
from platform.credentials.proxy.resolution import CredentialResolver, ResolvedCredential

__all__ = [
    "BasicAuthInjection",
    "BearerTokenInjection",
    "BodyFieldInjection",
    "CredentialExpired",
    "CredentialFieldsMissing",
    "CredentialRefresher",
    "CredentialResolver",
    "CredentialUnavailable",
    "CredentialUnreadable",
    "CredentialWouldCrossInClear",
    "EgressDenied",
    "HeaderInjection",
    "Injection",
    "InjectionRule",
    "InjectionRuleRegistry",
    "IntegrationNotDeclared",
    "MalformedProxyRequest",
    "OutboundRequest",
    "OutboundResponse",
    "OutboundSender",
    "PathSegmentInjection",
    "ProxyApp",
    "ProxyEngine",
    "ProxyError",
    "ProxyErrorReason",
    "ProxyHealth",
    "ProxyRequest",
    "QueryParameterInjection",
    "RefreshFailed",
    "RefreshedCredential",
    "RequestSigner",
    "ResolutionAuditor",
    "ResolutionRecord",
    "ResolvedCredential",
    "SignatureInjection",
    "TenantRateLimited",
    "TenantRateLimiter",
    "UpstreamUnreachable",
    "create_proxy_app",
    "needs_refresh",
]
