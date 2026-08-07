"""What a proposed change would do, computed by the service that would do it.

A surface offering "preview before saving" has two ways to answer. It can merge
the patch itself, which is a second implementation of inheritance that drifts
from the first, or it can ask the service — which is what this is. The value of
the answer is entirely in it coming from the same code path a real write takes.
"""

from __future__ import annotations

from typing import Any

import pytest

from platform.config_service.document import NodeDocument
from platform.config_service.service import ConfigService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, ConfigNodeKind, TenantScope

pytestmark = pytest.mark.anyio

ORG = "acme"
TEAM = "payments"


async def _service(
    *, org_values: dict[str, Any] | None = None, team_values: dict[str, Any] | None = None
) -> ConfigService:
    """Return a service over a two-node tree with the given stored documents."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    scope = TenantScope(org_id=ORG)
    async with gateway.begin(scope) as uow:
        root = await uow.config.get(ORG)
        assert root is not None
        if org_values is not None:
            await uow.config.upsert(
                ConfigNode(
                    node_id=ORG,
                    kind=root.kind,
                    name=root.name,
                    parent_id=None,
                    values=org_values,
                    version=root.version,
                )
            )
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM,
                kind=ConfigNodeKind.TEAM,
                name="Payments",
                parent_id=ORG,
                values=team_values if team_values is not None else {},
            )
        )
    return ConfigService(gateway=gateway, scope=scope)


async def test_a_preview_shows_the_merged_value_and_where_it_came_from() -> None:
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {"llm": {"temperature": 0.2}})

    assert preview.values["llm"] == {"model": "small", "temperature": 0.2}
    assert preview.provenance["llm.model"] == ORG
    assert preview.provenance["llm.temperature"] == TEAM


async def test_a_preview_stores_nothing() -> None:
    service = await _service()

    await service.preview_settings(TEAM, {"llm": {"model": "large"}})

    assert (await service.document(TEAM)).settings == {}
    assert "llm" not in (await service.resolve(TEAM)).values


async def test_a_preview_lists_only_the_fields_the_patch_would_change() -> None:
    service = await _service(team_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {"llm": {"model": "small", "temperature": 0.2}})

    assert [change.path for change in preview.changes] == ["llm.temperature"]
    assert preview.changes[0].before is None
    assert preview.changes[0].after == 0.2


async def test_a_preview_names_the_ancestor_locking_a_field_and_keeps_the_locked_value() -> None:
    service = await _service(
        org_values=NodeDocument.of(
            {"policies": {"masking": {"level": "standard"}}},
            locked=("policies.masking.level",),
        ).to_values()
    )

    preview = await service.preview_settings(TEAM, {"policies": {"masking": {"level": "off"}}})

    assert preview.locked == {"policies.masking.level": ORG}
    assert preview.values["policies"]["masking"]["level"] == "standard"


async def test_a_preview_reports_a_change_an_ancestor_puts_behind_an_approval() -> None:
    service = await _service(
        org_values=NodeDocument.of({}, approval_gated=("llm.model",)).to_values()
    )

    preview = await service.preview_settings(TEAM, {"llm": {"model": "large"}})

    assert preview.approval_gated == ("llm.model",)
    assert preview.requires_approval is True


async def test_a_preview_of_an_unrelated_field_needs_no_approval() -> None:
    service = await _service(
        org_values=NodeDocument.of({}, approval_gated=("llm.model",)).to_values()
    )

    preview = await service.preview_settings(TEAM, {"llm": {"temperature": 0.4}})

    assert preview.approval_gated == ()
    assert preview.requires_approval is False


async def test_an_empty_patch_previews_exactly_what_is_already_effective() -> None:
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {})
    effective = await service.resolve(TEAM)

    assert preview.values == effective.values
    assert preview.provenance == dict(effective.provenance)
    assert preview.changes == ()
