"""Setting a value a node already inherits, and clearing one it set.

Two answers a preview owes an operator, and neither is derivable from the
before-and-after table beside them.

The first is the most common configuration mistake there is: somebody sets a
field at a team, sees no change, and concludes the platform ignored them. The
value did change — from inherited to locally set — and resolved to exactly what
it resolved to before. Only the service knows that, because only the service
holds the parent's document, so the warning is computed here and travels with
the preview.

The second is the inverse operation, and it is *not* setting the field to the
parent's value. Clearing an override returns the field to whatever the parent
says next year; setting it to today's parent value freezes today's answer. They
resolve identically this afternoon and diverge the moment somebody edits the
parent, which is the whole reason inheritance exists.
"""

from __future__ import annotations

from typing import Any

import pytest

from platform.config_service.document import NodeDocument
from platform.config_service.errors import ChangeRequiresApproval, FieldLocked
from platform.config_service.service import ConfigService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, ConfigNodeKind, TenantScope

pytestmark = pytest.mark.anyio

ORG = "acme"
TEAM = "payments"


async def _service(
    *,
    org_values: dict[str, Any] | None = None,
    team_values: dict[str, Any] | None = None,
    gateway: FakePersistence | None = None,
) -> ConfigService:
    """Return a service over a two-node tree with the given stored documents."""
    gateway = gateway if gateway is not None else FakePersistence()
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


# --- Setting what is already inherited ---------------------------------------


async def test_setting_a_value_the_node_already_inherits_is_reported_as_redundant() -> None:
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {"llm": {"model": "small"}})

    assert [entry.path for entry in preview.redundant] == ["llm.model"]
    assert preview.redundant[0].value == "small"
    assert preview.redundant[0].inherited_from == ORG


async def test_a_redundant_set_is_still_a_change_so_the_diff_shows_it() -> None:
    # The write is real: the field moves from inherited to locally set, which is
    # why the operator sees a diff at all. What the warning adds is that the
    # *resolved* value does not move, which is the half they came for.
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {"llm": {"model": "small"}})

    assert [change.path for change in preview.changes] == ["llm.model"]
    assert preview.values["llm"]["model"] == "small"
    assert preview.provenance["llm.model"] == TEAM


async def test_setting_a_value_that_differs_from_the_inherited_one_is_not_redundant() -> None:
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {"llm": {"model": "large"}})

    assert preview.redundant == ()


async def test_a_field_no_ancestor_supplies_is_not_redundant() -> None:
    service = await _service()

    preview = await service.preview_settings(TEAM, {"llm": {"temperature": 0.2}})

    assert preview.redundant == ()


async def test_the_root_has_nothing_to_inherit_from_so_nothing_is_redundant() -> None:
    # A root node whose patch restates its own stored value changes nothing at
    # all, and "you already inherit this" would be a sentence about a parent
    # that does not exist.
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(ORG, {"llm": {"model": "small"}})

    assert preview.redundant == ()


async def test_a_locked_path_is_not_reported_as_redundant() -> None:
    # The value does not move because an ancestor forbade it, not because the
    # operator restated what they inherit. Reporting both would tell them to
    # remove an override the write never made.
    service = await _service(
        org_values=NodeDocument.of(
            {"policies": {"masking": {"level": "standard"}}},
            locked=("policies.masking.level",),
        ).to_values()
    )

    preview = await service.preview_settings(TEAM, {"policies": {"masking": {"level": "standard"}}})

    assert preview.redundant == ()
    assert preview.locked == {"policies.masking.level": ORG}


# --- Clearing a local override ------------------------------------------------


async def test_clearing_a_field_previews_the_value_it_reverts_to_and_the_level() -> None:
    service = await _service(
        org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values(),
        team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values(),
    )

    preview = await service.preview_settings(TEAM, {}, remove=("llm.model",))

    assert [entry.path for entry in preview.reverts] == ["llm.model"]
    assert preview.reverts[0].value == "small"
    assert preview.reverts[0].inherited_from == ORG
    assert preview.values["llm"]["model"] == "small"
    assert preview.provenance["llm.model"] == ORG


async def test_clearing_a_field_is_a_change_from_the_local_value_to_the_inherited_one() -> None:
    service = await _service(
        org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values(),
        team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values(),
    )

    preview = await service.preview_settings(TEAM, {}, remove=("llm.model",))

    assert [(change.path, change.before, change.after) for change in preview.changes] == [
        ("llm.model", "large", "small")
    ]


async def test_clearing_a_field_nothing_inherits_reverts_to_no_value_at_all() -> None:
    service = await _service(team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values())

    preview = await service.preview_settings(TEAM, {}, remove=("llm.model",))

    assert [entry.path for entry in preview.reverts] == ["llm.model"]
    assert preview.reverts[0].value is None
    assert preview.reverts[0].inherited_from == ""


async def test_clearing_a_field_that_is_not_set_locally_changes_nothing() -> None:
    service = await _service(org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values())

    preview = await service.preview_settings(TEAM, {}, remove=("llm.model",))

    assert preview.changes == ()
    assert preview.reverts == ()
    assert preview.values["llm"]["model"] == "small"


async def test_clearing_is_not_the_same_operation_as_setting_the_parent_value() -> None:
    # The distinction the whole control exists for. Both resolve to "small"
    # today; only one of them still resolves to whatever the parent says
    # tomorrow, and the provenance column is where an operator can see which
    # they are about to do.
    service = await _service(
        org_values=NodeDocument.of({"llm": {"model": "small"}}).to_values(),
        team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values(),
    )

    cleared = await service.preview_settings(TEAM, {}, remove=("llm.model",))
    set_to_parent = await service.preview_settings(TEAM, {"llm": {"model": "small"}})

    assert cleared.values == set_to_parent.values
    assert cleared.provenance["llm.model"] == ORG
    assert set_to_parent.provenance["llm.model"] == TEAM
    assert cleared.redundant == ()
    assert [entry.path for entry in set_to_parent.redundant] == ["llm.model"]


async def test_a_preview_of_a_removal_stores_nothing() -> None:
    service = await _service(team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values())

    await service.preview_settings(TEAM, {}, remove=("llm.model",))

    assert (await service.document(TEAM)).settings == {"llm": {"model": "large"}}


# --- Applying a removal -------------------------------------------------------
#
# These write, so they use fields the schema actually declares: an invented one
# is refused by validation before the removal is reached, and the test would be
# green for a reason that has nothing to do with clearing anything.


async def test_applying_a_removal_deletes_the_node_local_value() -> None:
    service = await _service(
        org_values=NodeDocument.of({"agents": {"tool_budget": 3}}).to_values(),
        team_values=NodeDocument.of(
            {"agents": {"tool_budget": 9, "max_iterations": 5}}
        ).to_values(),
    )

    await service.set_settings(TEAM, {}, remove=("agents.tool_budget",), actor_id="avery")

    assert (await service.document(TEAM)).settings == {"agents": {"max_iterations": 5}}
    assert (await service.resolve(TEAM)).value_at("agents.tool_budget") == 3


async def test_a_removal_that_empties_a_section_leaves_no_empty_section_behind() -> None:
    # An empty mapping is a value somebody set, as far as the merge is
    # concerned. Leaving one behind would make "this team overrides nothing"
    # render as a section with no fields in it.
    service = await _service(
        team_values=NodeDocument.of({"agents": {"tool_budget": 9}}).to_values()
    )

    await service.set_settings(TEAM, {}, remove=("agents.tool_budget",), actor_id="avery")

    assert (await service.document(TEAM)).settings == {}


async def test_a_removal_is_audited_as_a_cleared_field_naming_the_actor() -> None:
    gateway = FakePersistence()
    service = await _service(
        team_values=NodeDocument.of({"agents": {"tool_budget": 9}}).to_values(), gateway=gateway
    )

    await service.set_settings(TEAM, {}, remove=("agents.tool_budget",), actor_id="avery")

    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    cleared = [event for event in events if event.detail.get("field") == "agents.tool_budget"]
    assert len(cleared) == 1
    assert cleared[0].actor_id == "avery"
    assert cleared[0].resource_id == TEAM
    assert cleared[0].detail["previous_value"] == 9
    assert cleared[0].detail["new_value"] is None


async def test_a_removal_and_a_patch_in_one_write_both_take_effect() -> None:
    service = await _service(
        team_values=NodeDocument.of({"agents": {"tool_budget": 9, "max_iterations": 5}}).to_values()
    )

    await service.set_settings(
        TEAM,
        {"agents": {"max_iterations": 7}},
        remove=("agents.tool_budget",),
        actor_id="avery",
    )

    assert (await service.document(TEAM)).settings == {"agents": {"max_iterations": 7}}


async def test_removing_a_path_an_ancestor_locked_is_refused() -> None:
    # A locked path never had a local value to clear, and a clear that "succeeded"
    # would tell an operator they had lifted a constraint they cannot lift.
    service = await _service(
        org_values=NodeDocument.of(
            {"agents": {"tool_budget": 3}}, locked=("agents.tool_budget",)
        ).to_values()
    )

    with pytest.raises(FieldLocked):
        await service.set_settings(TEAM, {}, remove=("agents.tool_budget",), actor_id="avery")


async def test_removing_an_approval_gated_path_is_queued_rather_than_applied() -> None:
    # Deleting a gated field is a change to it. A clear that slipped past the
    # gate would make the gate advisory.
    service = await _service(
        org_values=NodeDocument.of({}, approval_gated=("agents.tool_budget",)).to_values(),
        team_values=NodeDocument.of({"agents": {"tool_budget": 9}}).to_values(),
    )

    with pytest.raises(ChangeRequiresApproval):
        await service.set_settings(TEAM, {}, remove=("agents.tool_budget",), actor_id="avery")

    assert (await service.document(TEAM)).settings == {"agents": {"tool_budget": 9}}
