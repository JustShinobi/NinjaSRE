"""The write path, end to end: what it refuses, what it queues, and what it records.

Every assertion here is about the *order* the service enforces, because that is
the only thing this class contributes that the modules beneath it do not. A
caller could compose validation, lock checking, persistence, and auditing by
hand; a caller doing it by hand is a caller who will one day store first and
validate afterwards.
"""

from __future__ import annotations

import pytest

from platform.config_service.catalogue import (
    CapabilityDescription,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
)
from platform.config_service.document import NodeDocument
from platform.config_service.errors import (
    ChangeRequiresApproval,
    ConfigInvalid,
    FieldLocked,
    LockConflict,
    NodeHasDescendants,
    UnknownNode,
)
from platform.config_service.field_policy import FieldPolicy
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.errors import ConcurrentModification
from platform.persistence.ports import (
    AuditOutcome,
    ConfigNode,
    PersistenceGateway,
    TenantScope,
)
from tests.unit.platform.config_service.conftest import (
    DIVISION,
    PRIMARY_ORG,
    SQUAD,
    TEAM,
    write_node,
)

pytestmark = pytest.mark.unit

ACTOR = "erik@example.test"


@pytest.fixture
def service(
    gateway: PersistenceGateway, scope: TenantScope, engine: GuardrailEngine
) -> ConfigService:
    return ConfigService(
        gateway=gateway,
        scope=scope,
        catalogue=StaticCatalogue.of(
            [
                CapabilityDescription(name="kubectl-get-pods", tags=("kubernetes",)),
                CapabilityDescription(name="rollout-restart", tags=("kubernetes", "remediation")),
                CapabilityDescription(name="placeholder"),
            ]
        ),
        integrations=StaticIntegrationDirectory.of(
            [IntegrationSchema(name="datadog"), IntegrationSchema(name="placeholder")]
        ),
        guardrails=engine,
    )


async def audit_events(gateway: PersistenceGateway, scope: TenantScope) -> tuple[object, ...]:
    """Return every audit event recorded for this tenant, newest first."""
    async with gateway.begin(scope) as uow:
        return await uow.audit.query(resource_kind="config_node", limit=100)


# --- The write applies, and is audited per field -----------------------------


async def test_a_write_merges_onto_what_is_there(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)
    await service.set_settings(TEAM, {"agents": {"max_iterations": 9}}, actor_id=ACTOR)

    document = await service.document(TEAM)
    assert document.settings == {"agents": {"tool_budget": 4, "max_iterations": 9}}


async def test_a_replacing_write_drops_what_it_does_not_mention(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)

    await service.set_settings(
        TEAM, {"agents": {"max_iterations": 9}}, actor_id=ACTOR, replace=True
    )

    assert (await service.document(TEAM)).settings == {"agents": {"max_iterations": 9}}


async def test_the_change_is_visible_in_the_next_resolution(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(DIVISION, {"agents": {"tool_budget": 3}}, actor_id=ACTOR)

    assert (await service.resolve(SQUAD)).value_at("agents.tool_budget") == 3
    assert (await service.resolve(SQUAD)).source_of("agents.tool_budget") == DIVISION


async def test_every_changed_field_is_audited_with_both_values(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    """FR-021."""
    await service.set_settings(TEAM, {"agents": {"tool_budget": 8}}, actor_id=ACTOR)
    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)

    events = await audit_events(gateway, scope)
    latest = events[0]
    assert latest.actor_id == ACTOR
    assert latest.resource_id == TEAM
    assert latest.detail["field"] == "agents.tool_budget"
    assert latest.detail["previous_value"] == 8
    assert latest.detail["new_value"] == 4


async def test_a_write_that_changes_nothing_records_nothing(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)
    before = len(await audit_events(gateway, scope))

    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)

    assert len(await audit_events(gateway, scope)) == before


# --- T027: validation precedes persistence, on every path --------------------


async def test_an_invalid_document_never_reaches_storage(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    with pytest.raises(ConfigInvalid):
        await service.set_settings(TEAM, {"agents": {"tool_budget": "eight"}}, actor_id=ACTOR)

    assert (await service.document(TEAM)).settings == {}


async def test_a_dangling_capability_reference_never_reaches_storage(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """SC-004."""
    with pytest.raises(ConfigInvalid, match="kubectl-teleport"):
        await service.set_settings(
            TEAM, {"capabilities": {"disabled": ["kubectl-teleport"]}}, actor_id=ACTOR
        )


async def test_a_secret_shaped_value_never_reaches_storage(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """SC-007."""
    with pytest.raises(ConfigInvalid, match="vault"):
        await service.set_settings(
            TEAM,
            {"integrations": {"active": [{"name": "datadog", "site": "ghp_" + "c" * 36}]}},
            actor_id=ACTOR,
        )

    assert (await service.document(TEAM)).settings == {}


# --- FR-022: the record of a refusal does not preserve what was refused ------


async def test_a_refused_write_is_audited_without_its_value(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    secret = "ghp_" + "d" * 36
    with pytest.raises(ConfigInvalid):
        await service.set_settings(
            TEAM,
            {"integrations": {"active": [{"name": "datadog", "site": secret}]}},
            actor_id=ACTOR,
        )

    events = await audit_events(gateway, scope)
    assert events
    assert events[0].outcome is AuditOutcome.DENIED
    assert all(secret not in str(event.detail) for event in events)


async def test_an_audited_value_that_matches_a_secret_rule_is_replaced(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    """FR-022, on the accepted path: the audit is not a second copy of the value.

    A capability *name* that happens to trip a rule is stored — the write was
    valid — but the audit row must not carry the matched text.
    """
    auditor = service._auditor  # noqa: SLF001 — the filter is the thing under test
    filtered = auditor.filtered("ghp_" + "e" * 36)

    assert "ghp_" not in filtered
    assert "github-token" in filtered


async def test_a_long_value_is_truncated_in_the_audit_trail(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    filtered = service._auditor.filtered("a" * 5_000)  # noqa: SLF001

    assert len(filtered) < 5_000
    assert "truncated" in filtered


# --- SC-002: the lock refusal an operator meets ------------------------------


async def test_a_write_to_a_locked_field_is_refused_naming_the_locking_node(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await write_node(
        gateway,
        scope,
        PRIMARY_ORG,
        parent_id=None,
        settings={"policies": {"masking": {"level": "strict"}}},
        locked=("policies.masking.level",),
    )

    with pytest.raises(FieldLocked) as raised:
        await service.set_settings(
            SQUAD, {"policies": {"masking": {"level": "off"}}}, actor_id=ACTOR
        )

    assert raised.value.locking_node_id == PRIMARY_ORG
    assert raised.value.path == "policies.masking.level"


async def test_the_locking_node_may_still_change_the_field_it_locked(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await write_node(
        gateway,
        scope,
        PRIMARY_ORG,
        parent_id=None,
        settings={"policies": {"masking": {"level": "strict"}}},
        locked=("policies.masking.level",),
    )

    await service.set_settings(
        PRIMARY_ORG, {"policies": {"masking": {"level": "off"}}}, actor_id=ACTOR
    )

    assert (await service.resolve(SQUAD)).value_at("policies.masking.level") == "off"


# --- FR-009: adding a lock over an existing override -------------------------


async def test_adding_a_lock_where_a_descendant_overrides_is_refused(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(TEAM, {"policies": {"masking": {"level": "off"}}}, actor_id=ACTOR)

    with pytest.raises(LockConflict) as raised:
        await service.set_policy(
            PRIMARY_ORG,
            FieldPolicy("policies.masking.level", locked=True),
            actor_id=ACTOR,
        )

    assert raised.value.overriding == (TEAM,)


async def test_adding_a_lock_nobody_overrides_is_recorded(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await service.set_policy(
        PRIMARY_ORG, FieldPolicy("policies.masking.level", locked=True), actor_id=ACTOR
    )

    assert (await service.document(PRIMARY_ORG)).policies.locked_paths() == (
        "policies.masking.level",
    )
    events = await audit_events(gateway, scope)
    assert events[0].action == "config.policy.set"


# --- FR-007: approval-gated changes are queued, not applied ------------------


async def test_a_gated_change_enters_the_queue_rather_than_taking_effect(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await service.set_policy(
        PRIMARY_ORG, FieldPolicy("agents.prompts", approval_gated=True), actor_id=ACTOR
    )

    with pytest.raises(ChangeRequiresApproval) as raised:
        await service.set_settings(
            TEAM, {"agents": {"prompts": {"investigator": "Be brief."}}}, actor_id=ACTOR
        )

    assert raised.value.paths == ("agents.prompts.investigator",)
    assert (await service.document(TEAM)).settings == {}

    async with gateway.begin(scope) as uow:
        pending = await uow.approvals.list_pending()
    assert [request.approval_id for request in pending] == [raised.value.approval_id]
    assert pending[0].arguments["gated_fields"] == ["agents.prompts.investigator"]


async def test_an_ungated_change_beside_a_gated_field_still_applies(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_policy(
        PRIMARY_ORG, FieldPolicy("agents.prompts", approval_gated=True), actor_id=ACTOR
    )

    await service.set_settings(TEAM, {"agents": {"tool_budget": 4}}, actor_id=ACTOR)

    assert (await service.document(TEAM)).settings == {"agents": {"tool_budget": 4}}


# --- FR-004: deletion and reparenting ----------------------------------------


async def test_deleting_a_node_with_descendants_is_refused(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    with pytest.raises(NodeHasDescendants):
        await service.delete_node(DIVISION)


async def test_deleting_a_leaf_is_allowed(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    assert await service.delete_node(SQUAD)

    with pytest.raises(UnknownNode):
        await service.resolve(SQUAD)


async def test_reparenting_changes_what_a_subtree_inherits(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(DIVISION, {"agents": {"tool_budget": 3}}, actor_id=ACTOR)
    assert (await service.resolve(SQUAD)).value_at("agents.tool_budget") == 3

    await service.reparent_node(TEAM, PRIMARY_ORG)

    assert (await service.resolve(SQUAD)).value_at("agents.tool_budget") is None


async def test_a_new_node_starts_empty_and_inherits(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(PRIMARY_ORG, {"agents": {"tool_budget": 6}}, actor_id=ACTOR)

    await service.create_node("team-search", name="Search", parent_id=DIVISION)

    resolved = await service.resolve("team-search")
    assert resolved.value_at("agents.tool_budget") == 6
    assert resolved.source_of("agents.tool_budget") == PRIMARY_ORG


# --- T047: two operators editing one node ------------------------------------


async def test_a_concurrent_write_is_refused_rather_than_merged(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    """Two operators editing one node have made a decision the store cannot make."""
    node = ConfigNode(
        node_id=TEAM,
        kind=(await service.document(TEAM)) and (await service._node(TEAM)).kind,  # noqa: SLF001
        name=TEAM,
        parent_id=DIVISION,
        values=NodeDocument.of({"agents": {"tool_budget": 1}}).to_values(),
        version=0,
    )

    await service.set_settings(TEAM, {"agents": {"tool_budget": 2}}, actor_id=ACTOR)

    async with gateway.begin(scope) as uow:
        with pytest.raises(ConcurrentModification):
            await uow.config.upsert(node)


# --- Templates through the service -------------------------------------------


async def test_applying_a_template_previews_then_applies_and_audits(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    diff = await service.preview_template(TEAM, "incident-triage-slack")
    assert not diff.empty

    await service.apply_template(TEAM, "incident-triage-slack", actor_id=ACTOR)

    resolved = await service.resolve(TEAM)
    assert resolved.config.surfaces.channels_for("critical")[0].channel == "#incidents"

    events = await audit_events(gateway, scope)
    assert events[0].action == "config.template.apply"
    assert events[0].detail["template"] == "incident-triage-slack"


async def test_a_template_cannot_overwrite_a_locked_field(
    service: ConfigService,
    gateway: PersistenceGateway,
    scope: TenantScope,
    four_levels: tuple[str, ...],
) -> None:
    await write_node(
        gateway,
        scope,
        PRIMARY_ORG,
        parent_id=None,
        settings={"agents": {"tool_budget": 2}},
        locked=("agents.tool_budget",),
    )

    with pytest.raises(FieldLocked):
        await service.apply_template(TEAM, "incident-triage-slack", actor_id=ACTOR)


# --- What the console asks for -----------------------------------------------


async def test_the_service_reports_what_a_team_can_run_and_why_not(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    await service.set_settings(
        TEAM, {"capabilities": {"disabled_tags": ["remediation"]}}, actor_id=ACTOR
    )

    view = await service.catalogue_view(TEAM)

    assert view.reason_for("kubectl-get-pods") is None
    reason = view.reason_for("rollout-restart")
    assert reason is not None and "remediation" in reason


async def test_the_service_reports_the_integration_forms_to_render(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    schemas = await service.integration_schemas(TEAM)

    assert {schema.name for schema in schemas} == {"datadog", "placeholder"}


async def test_the_service_lists_the_templates_it_can_apply(service: ConfigService) -> None:
    assert "incident-triage-slack" in service.template_names()
