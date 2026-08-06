"""The gated writes that already existed, routed through the one mechanism.

Two features queue changes today. The configuration service gates a write when a
field policy says so, and the knowledge queue holds an agent's proposal until
somebody reads it. Neither had conflict detection, decision-time permission
re-checking, a blast radius, or cross-surface closure, and building those three
times would have produced three of each.

So both route through the same service, and the adapters that do it are thin on
purpose: read the current value, and apply the approved one through the owning
package's own write path. The configuration schema stays validated by the
configuration service; the knowledge corpus stays written by the ingestor that
knows how to chunk and embed it.

The dependency runs one way. The configuration service declares a protocol for
"something takes my gated writes" and never imports the approval layer, which is
asserted here rather than left to a review.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from platform.approvals.appliers import (
    ApprovalQueueAdapter,
    ConfigurationApplier,
    PromptApplier,
    appliers_for,
)
from platform.approvals.models import ChangeState, ChangeTarget, ChangeType
from platform.approvals.service import ApprovalService
from platform.config_service.document import NodeDocument
from platform.config_service.errors import ChangeRequiresApproval
from platform.config_service.field_policy import FieldPolicy
from platform.config_service.service import ConfigService
from platform.persistence.ports import ConfigNode, PersistenceGateway, TenantScope

pytestmark = pytest.mark.unit

TEAM = "team-payments"
REQUESTER = "ada"

CONFIG_SERVICE_SOURCE = (
    Path(__file__).resolve().parents[4] / "platform" / "config_service" / "service.py"
)


@pytest.fixture
def config(gateway: PersistenceGateway, scope: TenantScope, clock: Any) -> ConfigService:
    """Return a configuration service with nothing taking its gated writes."""
    return ConfigService(gateway=gateway, scope=scope, clock=clock)


@pytest.fixture
def approvals(
    gateway: PersistenceGateway, scope: TenantScope, config: ConfigService, clock: Any
) -> ApprovalService:
    """Return an approval service that applies through the configuration service."""
    return ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers=appliers_for(config=config),
        clock=clock,
    )


async def gate(gateway: PersistenceGateway, scope: TenantScope, path: str) -> None:
    """Declare ``path`` approval-gated at the team node."""
    async with gateway.begin(scope) as uow:
        node = await uow.config.get(TEAM)
        assert node is not None
        document = NodeDocument.of_node(node).with_policies(
            NodeDocument.of_node(node).policies.with_policy(
                FieldPolicy(path=path, approval_gated=True)
            )
        )
        await uow.config.upsert(
            ConfigNode(
                node_id=node.node_id,
                kind=node.kind,
                name=node.name,
                parent_id=node.parent_id,
                values=document.to_values(),
                version=node.version,
            )
        )


# --- The dependency direction ------------------------------------------------


def test_the_configuration_service_does_not_import_the_approval_layer() -> None:
    """It declares a protocol for what takes its gated writes, and nothing more.

    Importing the approval layer would make the two packages inseparable and
    would put a cycle in the import graph, since the approval layer needs the
    hierarchy to compute a blast radius.
    """
    tree = ast.parse(CONFIG_SERVICE_SOURCE.read_text(encoding="utf-8"))

    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any(name.startswith("platform.approvals") for name in imported)


# --- Configuration (T047) ----------------------------------------------------


async def test_a_gated_configuration_write_is_queued_as_a_pending_change(
    gateway: PersistenceGateway,
    scope: TenantScope,
    approvals: ApprovalService,
    clock: Any,
) -> None:
    await gate(gateway, scope, "policies.masking.level")
    service = ConfigService(
        gateway=gateway,
        scope=scope,
        approvals=ApprovalQueueAdapter(service=approvals),
        clock=clock,
    )

    with pytest.raises(ChangeRequiresApproval) as raised:
        await service.set_settings(
            TEAM, {"policies": {"masking": {"level": "off"}}}, actor_id=REQUESTER
        )

    queued = await approvals.get(raised.value.approval_id)
    assert queued.change_type is ChangeType.CONFIGURATION
    assert queued.target.identifier == TEAM
    assert queued.requester == REQUESTER
    assert queued.state is ChangeState.PENDING


async def test_the_current_value_stays_in_effect_until_the_change_is_approved(
    gateway: PersistenceGateway,
    scope: TenantScope,
    approvals: ApprovalService,
    config: ConfigService,
    clock: Any,
) -> None:
    """Acceptance scenario 1, end to end through both services."""
    await config.set_settings(TEAM, {"policies": {"masking": {"level": "strict"}}}, actor_id="ops")
    await gate(gateway, scope, "policies.masking.level")

    service = ConfigService(
        gateway=gateway,
        scope=scope,
        approvals=ApprovalQueueAdapter(service=approvals),
        clock=clock,
    )
    with pytest.raises(ChangeRequiresApproval):
        await service.set_settings(
            TEAM, {"policies": {"masking": {"level": "off"}}}, actor_id=REQUESTER
        )

    document = await service.document(TEAM)
    assert document.settings["policies"]["masking"]["level"] == "strict"


async def test_approving_a_configuration_change_applies_it_through_its_own_service(
    gateway: PersistenceGateway,
    scope: TenantScope,
    approvals: ApprovalService,
    config: ConfigService,
    clock: Any,
    as_reviewer: Any,
) -> None:
    """Acceptance scenario 3: it applies, and it applies validated."""
    await config.set_settings(TEAM, {"policies": {"masking": {"level": "strict"}}}, actor_id="ops")
    queued = await approvals.queue(
        change_type=ChangeType.CONFIGURATION,
        target=ChangeTarget(identifier=TEAM, node_id=TEAM, path="policies.masking.level"),
        proposed={"policies": {"masking": {"level": "standard"}}},
        requester=REQUESTER,
        rationale="the regulator accepted the lower level",
    )

    decided = await approvals.decide(queued.change_id, **as_reviewer(), approve=True)

    assert decided.state is ChangeState.APPROVED
    document = await config.document(TEAM)
    assert document.settings["policies"]["masking"]["level"] == "standard"


async def test_a_configuration_change_conflicts_when_somebody_else_edits_first(
    gateway: PersistenceGateway,
    scope: TenantScope,
    approvals: ApprovalService,
    config: ConfigService,
    as_reviewer: Any,
) -> None:
    """The machinery the configuration service did not have on its own."""
    from platform.approvals.errors import ChangeConflicted

    await config.set_settings(TEAM, {"policies": {"masking": {"level": "strict"}}}, actor_id="ops")
    queued = await approvals.queue(
        change_type=ChangeType.CONFIGURATION,
        target=ChangeTarget(identifier=TEAM, node_id=TEAM, path="policies.masking.level"),
        proposed={"policies": {"masking": {"level": "standard"}}},
        requester=REQUESTER,
        rationale="because",
    )

    await config.set_settings(
        TEAM, {"policies": {"masking": {"level": "off"}}}, actor_id="somebody"
    )

    with pytest.raises(ChangeConflicted):
        await approvals.decide(queued.change_id, **as_reviewer(), approve=True)

    document = await config.document(TEAM)
    assert document.settings["policies"]["masking"]["level"] == "off"


async def test_a_deleted_node_reads_as_a_missing_target(config: ConfigService) -> None:
    applier = ConfigurationApplier(service=config)

    assert await applier.read(ChangeTarget(identifier="team-that-never-existed")) is None


async def test_the_applier_map_holds_only_what_a_deployment_can_apply(
    config: ConfigService,
) -> None:
    """A change type with no applier cannot be queued, which is the right failure."""
    built = appliers_for(config=config)

    assert set(built) == {ChangeType.CONFIGURATION, ChangeType.PROMPT, ChangeType.CAPABILITY}
    assert ChangeType.REMEDIATION not in built
    assert isinstance(built[ChangeType.PROMPT], PromptApplier)


async def test_an_empty_deployment_wires_nothing() -> None:
    assert appliers_for() == {}


# --- Remediation, reserved (T049) --------------------------------------------


def test_remediation_has_a_renderer_and_a_gate_but_no_applier() -> None:
    """What "reserved" means, concretely.

    A remediation can already be described to a reviewer and can already be
    gated by side-effect level. What it cannot do is apply, which is exactly the
    piece feature 017 owns — and wiring it is one entry in the applier map
    rather than a second approval mechanism.
    """
    from config.constants.security import SIDE_EFFECT_DESTRUCTIVE
    from platform.approvals.diff.renderers import RENDERERS
    from platform.approvals.policy import SecurityPolicy

    assert ChangeType.REMEDIATION in RENDERERS
    assert SecurityPolicy(
        require_approval_for_side_effect_levels=(SIDE_EFFECT_DESTRUCTIVE,)
    ).requires_approval_for_level(SIDE_EFFECT_DESTRUCTIVE)
