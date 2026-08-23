"""The investigator is built before the configuration it depends on is read.

``build_deployment`` composes the runner — and with it the model client, which
``get_llm`` resolves and caches — while the process still knows nothing but its
environment. The operator's model choice is published afterwards, by
``gateway/http/serve.py``'s boot, and the vault's provider keys later still, by
the lifespan.

So fixing the role the investigator asks for was necessary and not sufficient:
the client had already been built, from an empty binding table and an
environment-backed resolver, and was being handed back from a cache. In staging
that meant every investigation kept calling a provider named in the manifest
whose address no longer existed, and degrading on its first iteration, with the
configured provider sitting in the tree unread.

Rebuilding it once, after both are true, is the whole fix. It happens where the
rest of the composition happens rather than in ``build_deployment``, because
what it needs — the configuration tree and the vault — is what
``build_deployment`` deliberately does not have.
"""

from __future__ import annotations

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    NINJASRE_INVESTIGATOR_ENV,
)
from config.constants.llm import ANTHROPIC_API_KEY_ENV, NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import (
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV,
    NINJASRE_DATABASE_URL_ENV,
)
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from core.llm.factory import (
    publish_configured_bindings,
    reset_configured_bindings,
    reset_factory,
)
from gateway.http.runtime import recompose_investigator
from gateway.runtime.factory import build_investigator
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.unit

_FACTORY_REFERENCE = "gateway.runtime.factory:build_investigator"

_ENVIRON = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_LLM_PROVIDER_ENV: "anthropic",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "A" * 43 + "=",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
    NINJASRE_INVESTIGATOR_ENV: _FACTORY_REFERENCE,
}


class _State:
    """Only what the recomposition touches."""

    def __init__(self, investigator: object) -> None:
        self.investigator = investigator
        self.gateway = FakePersistence()
        self.guardrails = GuardrailEngine()
        self.broker = RunEventBroker()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENVIRON.items():
        monkeypatch.setenv(key, value)
    reset_configured_bindings()
    reset_factory()
    yield
    reset_configured_bindings()
    reset_factory()


def test_the_runner_built_at_boot_cannot_see_a_binding_published_after_it() -> None:
    """The state this exists to correct, asserted so the fix cannot be read as
    unnecessary."""
    early = build_investigator()
    publish_configured_bindings({"investigator": ("google_gemini", "gemini-flash-latest")})

    assert early.llm.provider_id == "anthropic"


def test_recomposing_gives_the_deployment_the_model_its_configuration_names() -> None:
    state = _State(build_investigator())
    publish_configured_bindings({"investigator": ("google_gemini", "gemini-flash-latest")})
    reset_factory()

    recompose_investigator(state, environ=_ENVIRON)

    assert state.investigator.llm.provider_id == "google_gemini"
    assert state.investigator.llm.model_id == "gemini-flash-latest"


def test_a_deployment_that_names_no_factory_is_left_with_its_stand_in() -> None:
    """Recomposition must not turn "nothing is composed" into something that
    looks composed — the checklist and the route both read that distinction."""
    from gateway.http.asgi import UnconfiguredInvestigator

    state = _State(UnconfiguredInvestigator())

    recompose_investigator(state, environ={})

    assert isinstance(state.investigator, UnconfiguredInvestigator)
