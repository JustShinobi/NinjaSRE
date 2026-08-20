"""Building the credential proxy from the operator's configuration.

Everything the proxy needs comes from two places and neither of them is a
guess. The store comes from ``NINJASRE_DATABASE_URL``; the credential schemas
and injection rules come from whichever integrations are installed, read
through ``integrations.registry`` rather than a list somebody maintains.

That second half is why this lives at tier 1. ``platform/`` may not import
``integrations/``, so the rules have to be handed *down* — which is exactly the
indirection ``InjectionRuleRegistry`` documents, and this is the code on the
other side of it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from gateway.proxy.sender import HttpOutboundSender
from integrations.registry import credential_schemas, injection_rules
from platform.credentials.proxy.app import ProxyApp, create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.credentials.proxy.resolution import CredentialResolver
from platform.persistence.ports.transaction import PersistenceGateway
from platform.persistence.postgres.gateway import PostgresPersistence
from platform.startup.validation import validate_proxy


def build_proxy_engine(gateway: PersistenceGateway) -> ProxyEngine:
    """Return the engine this deployment's installed integrations describe.

    Takes the store rather than building one, because the dev profile mounts
    this alongside the application and the two must share a connection pool
    rather than opening a second one against the same database.
    """
    return ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=credential_schemas()),
        rules=injection_rules(),
        sender=HttpOutboundSender(),
        auditor=ResolutionAuditor(gateway=gateway),
        limiter=TenantRateLimiter(),
    )


def build_proxy_app(
    environ: Mapping[str, str] | None = None,
) -> tuple[ProxyApp, PostgresPersistence]:
    """Return the standalone proxy service and the store it holds open.

    The store comes back with it because whoever starts this process is the one
    that has to dispose of the connection pool, and a composition root that
    hides what it opened leaves a pool nobody closes.

    Raises ``ConfigurationInvalid`` when validation finds something fatal.

    Validates against ``validate_proxy`` rather than the deployment-wide
    ``validate``: the proxy brokers credentials and never calls a model, so a
    missing model provider is not this process's problem to refuse over — that
    minimum-viable-configuration rule belongs to ``app`` and ``console``, the
    processes that actually call one.
    """
    source = dict(environ if environ is not None else os.environ)

    report = validate_proxy(source)
    report.raise_if_invalid()

    store = PostgresPersistence.from_url(source[NINJASRE_DATABASE_URL_ENV])
    return create_proxy_app(build_proxy_engine(store)), store


__all__ = ["build_proxy_app", "build_proxy_engine"]
