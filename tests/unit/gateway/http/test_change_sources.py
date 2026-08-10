"""Where "what changed" is read from, configured rather than compiled in.

Two shapes answer that question and a deployment may have either, both, or
neither: the repository's own apply record — what the tooling actually put on
the cluster — and a git host's commit listing. Which of them this deployment has
is not a property of the build, so it is a setting in the configuration tree,
resolved at the root and composed once at startup.

Neither is the same as an empty answer. A deployment that configured no change
source reports "nothing was consulted"; a configured source that found nothing
reports "nothing changed". Composing an *absent* source as a present one that
returns nothing would collapse the two, and the collapse is silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.tools.changes import binding
from gateway.http.change_sources import change_sources_from, compose_change_sources
from gateway.http.state import GatewayState
from platform.config_service.document import NodeDocument
from platform.config_service.schema.root import RootConfig
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, TenantScope

pytestmark = pytest.mark.anyio

ORG = "acme"


def _settings(values: dict[str, object]) -> RootConfig:
    return RootConfig.of({"policies": {"changes": values}})


# --- Reading the setting ------------------------------------------------------


def test_a_deployment_that_configured_nothing_composes_no_source() -> None:
    # Not one source that answers nothing: "nobody was asked" and "nobody had
    # anything" are different findings and lead somewhere different.
    assert change_sources_from(_settings({}).policies.changes) == ()


def test_a_repository_path_composes_the_apply_record_source(tmp_path: Path) -> None:
    sources = change_sources_from(_settings({"repository_path": str(tmp_path)}).policies.changes)

    assert [type(source).__name__ for source in sources] == ["InfraApplySource"]


def test_a_vendor_and_a_repository_compose_a_git_host_source() -> None:
    sources = change_sources_from(
        _settings({"git_host": {"vendor": "github", "repository": "acme/infra"}}).policies.changes
    )

    assert [type(source).__name__ for source in sources] == ["GitHostChangeSource"]
    assert sources[0].repository == "acme/infra"


def test_both_configured_compose_both_with_the_apply_record_first() -> None:
    # The apply record answers "did anybody apply this", which a commit listing
    # cannot. Asking it first is what puts the stronger evidence at the top of
    # the answer.
    sources = change_sources_from(
        _settings(
            {
                "repository_path": "/srv/infra",
                "git_host": {"vendor": "gitlab", "repository": "acme/infra"},
            }
        ).policies.changes
    )

    assert [type(source).__name__ for source in sources] == [
        "InfraApplySource",
        "GitHostChangeSource",
    ]


def test_a_vendor_with_no_repository_composes_nothing() -> None:
    # A vendor names which client to build; the repository names what to read.
    # Half a configuration is not a source, and composing one would produce a
    # listing request for the empty string.
    assert change_sources_from(_settings({"git_host": {"vendor": "github"}}).policies.changes) == ()


def test_a_vendor_nothing_can_read_is_refused_where_it_is_configured() -> None:
    from integrations._base.changes import UnsupportedGitHost

    with pytest.raises(UnsupportedGitHost):
        change_sources_from(
            _settings(
                {"git_host": {"vendor": "sourceforge", "repository": "acme/infra"}}
            ).policies.changes
        )


# --- Composing it onto the running deployment ---------------------------------


async def _state(values: dict[str, object] | None = None) -> GatewayState:
    """Return a state over an organisation whose root carries ``values``."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    if values is not None:
        async with gateway.begin(TenantScope(org_id=ORG)) as uow:
            root = await uow.config.get(ORG)
            assert root is not None
            await uow.config.upsert(
                ConfigNode(
                    node_id=ORG,
                    kind=root.kind,
                    name=root.name,
                    parent_id=None,
                    values=NodeDocument.of({"policies": {"changes": values}}).to_values(),
                    version=root.version,
                )
            )
    return GatewayState(
        gateway=gateway,
        tokens=None,  # type: ignore[arg-type]
        investigator=None,  # type: ignore[arg-type]
    )


async def test_startup_puts_the_configured_sources_on_the_state(tmp_path: Path) -> None:
    state = await _state({"repository_path": str(tmp_path)})

    await compose_change_sources(state, org_id=ORG)

    assert [type(source).__name__ for source in state.change_sources] == ["InfraApplySource"]


async def test_startup_binds_the_capability_to_the_same_sources(tmp_path: Path) -> None:
    state = await _state({"repository_path": str(tmp_path)})
    previous = binding.current()
    try:
        await compose_change_sources(state, org_id=ORG)

        assert binding.current() is not None
    finally:
        binding.restore(previous)


async def test_a_deployment_that_configured_none_leaves_the_capability_unbound() -> None:
    # The capability's own contract: an unbound tool reports that no change
    # source is configured, which is the honest answer and the one the operator
    # can act on.
    state = await _state()
    previous = binding.bind(None)
    try:
        await compose_change_sources(state, org_id=ORG)

        assert binding.current() is None
        assert state.change_sources == ()
    finally:
        binding.restore(previous)


async def test_a_change_source_written_through_the_configuration_route_is_readable_back(
    tmp_path: Path,
) -> None:
    # The half that closes the loop: what the console writes into the tree is
    # what composition reads out of it. Without this the setting is a field
    # nothing consumes, which is worse than no setting at all.
    from platform.config_service.service import ConfigService

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    scope = TenantScope(org_id=ORG)
    service = ConfigService(gateway=gateway, scope=scope)

    await service.set_settings(
        ORG,
        {
            "policies": {
                "changes": {
                    "repository_path": str(tmp_path),
                    "git_host": {"vendor": "github", "repository": "acme/infra"},
                }
            }
        },
        actor_id="ada",
    )

    effective = await service.resolve(ORG)
    assert [
        type(source).__name__ for source in change_sources_from(effective.config.policies.changes)
    ] == ["InfraApplySource", "GitHostChangeSource"]


async def test_a_misconfigured_vendor_does_not_stop_the_gateway_from_starting() -> None:
    # Composition happens at startup, and a refusal here would mean a typo in one
    # optional setting takes the whole deployment down — including the console
    # somebody would fix it from.
    state = await _state({"git_host": {"vendor": "sourceforge", "repository": "acme/infra"}})

    await compose_change_sources(state, org_id=ORG)

    assert state.change_sources == ()
