"""A write is refused for what the *chain* becomes, not only for what the node says.

Feature 059 left this open and said so plainly: ``ConfigValidator`` validates a
node's own document, so a four-level chain whose nodes each write a thousand
tokens of operating context stores happily and resolves to four thousand. What
happens then is safe — the merged section is refused at resolution and the
deployment sends no context at all — and silent, which is the problem. The only
place it surfaced was the preview, which the person doing the write may never
have opened.

**Only what the write introduces is refused.** A chain that is already invalid
must not block every unrelated edit beneath it: somebody fixing a typo three
levels down did not cause the overage and cannot be the one to answer for it. So
the merged document is validated twice — as it resolves now, and as it would
resolve — and the difference is what the write is refused for.
"""

from __future__ import annotations

import pytest

from config.constants.agents import OPERATING_CONTEXT_TOKEN_BUDGET
from platform.config_service.errors import ConfigInvalid
from platform.config_service.service import ConfigService
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.config_service.conftest import DIVISION, SQUAD, TEAM, write_node

pytestmark = pytest.mark.unit

#: Roughly a third of the budget each, in the estimator the budget is set in.
_THIRD = "word " * (OPERATING_CONTEXT_TOKEN_BUDGET // 2)


def context(body: str, name: str = "Estate") -> dict[str, object]:
    """Return the settings patch that writes one operating-context section."""
    return {"agents": {"operating_context": {"sections": {name: body}}}}


def service(gateway: PersistenceGateway, scope: TenantScope) -> ConfigService:
    """Return the configuration service under test."""
    return ConfigService(gateway=gateway, scope=scope)


async def test_a_write_that_only_crosses_the_bound_once_merged_is_refused(
    gateway: PersistenceGateway, scope: TenantScope, four_levels: tuple[str, ...]
) -> None:
    """The bound is enforced at the write that crosses it, not only in the preview."""
    await write_node(gateway, scope, DIVISION, parent_id=four_levels[0])
    config = service(gateway, scope)
    await config.set_settings(DIVISION, context(_THIRD, name="Division"), actor_id="operator")

    with pytest.raises(ConfigInvalid) as refusal:
        await config.set_settings(TEAM, context(_THIRD, name="Team"), actor_id="operator")

    assert "operating-context budget" in str(refusal.value)


async def test_the_node_that_was_refused_stored_nothing(
    gateway: PersistenceGateway, scope: TenantScope, four_levels: tuple[str, ...]
) -> None:
    """Validation precedes persistence on this path too."""
    config = service(gateway, scope)
    await config.set_settings(DIVISION, context(_THIRD, name="Division"), actor_id="operator")

    with pytest.raises(ConfigInvalid):
        await config.set_settings(TEAM, context(_THIRD, name="Team"), actor_id="operator")

    assert (await config.document(TEAM)).settings == {}


async def test_a_write_that_fits_the_whole_chain_is_stored(
    gateway: PersistenceGateway, scope: TenantScope, four_levels: tuple[str, ...]
) -> None:
    """The check refuses an overage, not the section."""
    config = service(gateway, scope)
    await config.set_settings(
        DIVISION, context("The estate is one cluster.", "Division"), actor_id="operator"
    )

    stored = await config.set_settings(
        TEAM, context("Payments owns checkout.", "Team"), actor_id="operator"
    )

    assert stored.node_id == TEAM
    resolved = await config.resolve(TEAM)
    assert set(resolved.config.agents.operating_context.sections) == {"Division", "Team"}


async def test_an_unrelated_edit_below_an_already_broken_chain_still_works(
    gateway: PersistenceGateway, scope: TenantScope, four_levels: tuple[str, ...]
) -> None:
    """Somebody fixing a typo three levels down did not cause the overage.

    The chain is put over budget by writing the ancestors' documents directly,
    which is how a deployment reaches this state: two nodes each stored a
    section that was within budget on its own, before this check existed.
    """
    await write_node(
        gateway, scope, DIVISION, parent_id=four_levels[0], settings=context(_THIRD, "Division")
    )
    await write_node(gateway, scope, TEAM, parent_id=DIVISION, settings=context(_THIRD, "Team"))
    config = service(gateway, scope)

    stored = await config.set_settings(SQUAD, {"agents": {"max_iterations": 7}}, actor_id="op")

    assert (await config.document(SQUAD)).settings["agents"]["max_iterations"] == 7
    assert stored.node_id == SQUAD
