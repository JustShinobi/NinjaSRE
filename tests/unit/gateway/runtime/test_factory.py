"""``build_investigator`` is the no-argument reference an operator can name.

Before this feature, the only implementer of ``InvestigationRunner`` in the
whole repository was the refuser that names what is missing — precondition 9
of this feature's own specification. These tests prove the opposite is now
true: naming ``gateway.runtime.factory:build_investigator`` composes a real
runner, without the operator writing a line of code, and that composed
runner is what the deployment's three "can this investigate?" surfaces agree
on.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import Registry
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
from gateway.runtime.factory import build_investigator
from gateway.runtime.investigator import ReActInvestigationRunner

pytestmark = pytest.mark.unit

_ENVIRON = {
    NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_LLM_PROVIDER_ENV: "anthropic",
    ANTHROPIC_API_KEY_ENV: "sk-ant-not-a-real-key",
    NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: "A" * 43 + "=",
    NINJASRE_CREDENTIAL_PROXY_URL_ENV: "http://proxy:8422",
}


@pytest.fixture(autouse=True)
def _isolated_llm_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give this file its own client cache and set the provider it names.

    ``core.llm.factory`` caches clients process-wide, keyed by provider and
    model — not by credential — so a client another test built for the same
    provider would otherwise be handed back here unread.
    """
    for key, value in _ENVIRON.items():
        monkeypatch.setenv(key, value)
    reset_factory()


def test_the_investigator_runs_on_the_model_configuration_bound_to_it() -> None:
    """The role name is the whole of this, and it was wrong in the one place it counted.

    ``gateway/http/serve.py`` reads the configuration tree at boot and publishes
    the operator's choice under the role it is stored against — ``investigator``.
    This factory asked for the default role, which nothing binds, so the answer
    fell through to the environment every time. An operator who chose a provider
    in the console watched every investigation run on whatever the manifest
    happened to say, with no indication anywhere that their choice was being
    read under a different name.
    """
    publish_configured_bindings({"investigator": ("google_gemini", "gemini-flash-latest")})
    try:
        runner = build_investigator()
    finally:
        reset_configured_bindings()

    assert isinstance(runner, ReActInvestigationRunner)
    assert runner.llm.provider_id == "google_gemini"
    assert runner.llm.model_id == "gemini-flash-latest"


def test_the_environment_still_answers_for_a_deployment_that_configured_nothing() -> None:
    """Which is every deployment until somebody opens the first-run screen."""
    reset_configured_bindings()

    runner = build_investigator()

    assert runner.llm.provider_id == "anthropic"


def test_build_investigator_takes_no_argument_and_returns_a_real_runner() -> None:
    """The one call ``NINJASRE_INVESTIGATOR=gateway.runtime.factory:build_investigator`` makes."""
    runner = build_investigator()

    assert isinstance(runner, ReActInvestigationRunner)


def test_the_composed_runner_carries_a_provider_client_from_the_abstraction() -> None:
    runner = build_investigator()

    assert runner.llm.provider_id == "anthropic"
    assert runner.llm.model_id


def test_the_composed_runner_carries_the_validated_capability_registry() -> None:
    runner = build_investigator()

    assert isinstance(runner.registry, Registry)
    assert len(runner.registry.tools) > 0


def test_naming_this_factory_is_what_the_deployment_composes_end_to_end() -> None:
    """The same object the entry point installs, through ``build_deployment``.

    Ties T015 to the pre-existing three-surface agreement
    (``gateway.http.runtime.runtime_composed``): the setup checklist, the
    self-check, and the route that starts an investigation all ask this one
    question of whatever the composition root actually built.
    """
    from gateway.http.asgi import UnconfiguredInvestigator, build_deployment
    from gateway.http.runtime import runtime_composed

    environ = {
        **_ENVIRON,
        NINJASRE_INVESTIGATOR_ENV: "gateway.runtime.factory:build_investigator",
    }

    deployment = build_deployment(environ)

    assert isinstance(deployment.state.investigator, ReActInvestigationRunner)
    assert not isinstance(deployment.state.investigator, UnconfiguredInvestigator)
    assert runtime_composed(deployment.state) is True
