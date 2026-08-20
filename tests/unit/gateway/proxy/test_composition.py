"""The proxy's own composition root refuses on its own terms, not the app's.

``build_proxy_app`` is what ``python -m gateway.proxy`` actually calls at
boot, so this is the level the real crash-loop happened at: a deployment with
no model provider configured anywhere used to make the credential proxy
refuse to start, even though the proxy never calls a model. Testing at
``validate_proxy`` alone would prove the check is right without proving this
module actually wires it in — ``build_proxy_app`` still imported ``validate``
by name, so a passing check does not by itself prove a passing boot.

No container runtime is needed. ``PostgresPersistence.from_url`` builds a
SQLAlchemy async engine, and an engine pool is lazy — nothing here opens a
socket, so the assertions hold with no Postgres listening anywhere.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import NINJASRE_DEPLOYMENT_PROFILE_ENV
from config.constants.llm import NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from gateway.proxy.composition import build_proxy_app
from platform.startup.errors import ConfigurationInvalid

pytestmark = pytest.mark.unit

#: What ``docker-compose.yml`` actually gives the proxy container today —
#: no model provider anywhere in it, which is exactly what used to crash-loop.
COMPOSE_PROXY_ENVIRONMENT = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: "standard",
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre:ninjasre@postgres:5432/ninjasre",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}


async def test_a_configuration_with_no_model_provider_boots_the_proxy() -> None:
    """The exact crash-loop, reproduced and closed at the real entry point."""
    app, store = build_proxy_app(COMPOSE_PROXY_ENVIRONMENT)
    try:
        assert app.engine is not None
    finally:
        await store.close()


async def test_a_configuration_missing_the_proxys_own_database_still_refuses() -> None:
    """Narrowed, not deleted: something that is genuinely the proxy's own
    still stops the boot, at the same entry point that now accepts a missing
    provider. A test that only proved the first would pass equally if
    ``build_proxy_app`` validated nothing at all."""
    environ = {
        key: value
        for key, value in COMPOSE_PROXY_ENVIRONMENT.items()
        if key != NINJASRE_DATABASE_URL_ENV
    }

    with pytest.raises(ConfigurationInvalid) as excinfo:
        build_proxy_app(environ)

    assert NINJASRE_DATABASE_URL_ENV in excinfo.value.settings
    assert NINJASRE_LLM_PROVIDER_ENV not in excinfo.value.settings, (
        "the proxy's own boot must not also blame the model provider"
    )
