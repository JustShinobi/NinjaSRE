"""Autonomy is configured through the configuration service, not beside it.

Driven against the real ``ConfigService`` over the real in-memory gateway, so
what is asserted is the actual merge, the actual lock check, the actual
approval gate and the actual save-time validation — not a description of them.
That is the point of expressing policy there: a second mechanism for the most
safety-critical setting in the system would have to re-earn every one of these.
"""

from __future__ import annotations

from typing import Any

import pytest

from platform.autonomy.configuration import policy_set_of, settings_of
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.resolution import resolve
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.config_service.catalogue import (
    CapabilityDescription,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
)
from platform.config_service.errors import ChangeRequiresApproval, ConfigInvalid, FieldLocked
from platform.config_service.field_policy import FieldPolicy
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.autonomy.conftest import NOON, action, subject
from tests.unit.platform.config_service.conftest import DIVISION, PRIMARY_ORG, TEAM, write_node

pytestmark = pytest.mark.contract

ACTOR = "ada@example.test"

AUTONOMY_PATH = "policies.autonomy"


@pytest.fixture
def service(
    gateway: PersistenceGateway, scope: TenantScope, engine: GuardrailEngine
) -> ConfigService:
    """Return the real service, over the real gateway and the shipped ruleset."""
    return ConfigService(
        gateway=gateway,
        scope=scope,
        catalogue=StaticCatalogue.of([CapabilityDescription(name="restart_workload")]),
        integrations=StaticIntegrationDirectory.of([IntegrationSchema(name="datadog")]),
        guardrails=engine,
    )


def a_rule(level: str, **scope: Any) -> dict[str, Any]:
    """Return one rule in the shape the configuration takes."""
    return {"scope": {"kind": "deployment", **scope}, "level": level}


async def test_a_teams_policy_is_the_merge_of_its_own_and_its_parents(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """Inherited, not restated. The whole reason policy lives here."""
    await service.set_settings(
        PRIMARY_ORG,
        {"policies": {"autonomy": {"rules": [a_rule("propose_only")], "dry_run": True}}},
        actor_id=ACTOR,
    )
    await service.set_settings(
        DIVISION,
        {
            "policies": {
                "autonomy": {
                    "rules": [
                        {
                            "scope": {"kind": "capability", "capability": "restart_workload"},
                            "level": "act_and_report",
                        }
                    ]
                }
            }
        },
        actor_id=ACTOR,
    )

    effective = await service.resolve(TEAM)
    policies = policy_set_of(effective.config.policies, source=effective.node_id)

    # The division's list replaces the organisation's — a list is a value, and
    # the merge says so — while ``dry_run`` is inherited untouched.
    assert policies.dry_run is True
    assert [rule.level for rule in policies.rules] == [AutonomyLevel.ACT_AND_REPORT]
    assert policies.rules[0].source == TEAM

    resolved = resolve(action(), policies, at=NOON)
    assert resolved.level is AutonomyLevel.ACT_AND_REPORT
    assert resolved.dry_run


async def test_a_locked_autonomy_field_cannot_be_relaxed_by_a_team(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """The lock the configuration service already implements, applied here."""
    await service.set_settings(
        PRIMARY_ORG,
        {"policies": {"autonomy": {"rules": [a_rule("propose_only")]}}},
        actor_id=ACTOR,
    )
    await service.set_policy(
        PRIMARY_ORG,
        FieldPolicy(path=f"{AUTONOMY_PATH}.rules", locked=True),
        actor_id=ACTOR,
    )

    with pytest.raises(FieldLocked) as refused:
        await service.set_settings(
            TEAM,
            {"policies": {"autonomy": {"rules": [a_rule("act_and_report")]}}},
            actor_id=ACTOR,
        )
    assert PRIMARY_ORG in str(refused.value)

    effective = await service.resolve(TEAM)
    policies = policy_set_of(effective.config.policies)
    assert [rule.level for rule in policies.rules] == [AutonomyLevel.PROPOSE_ONLY]


async def test_raising_autonomy_can_be_gated_behind_an_approval(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """A posture change is a change, and the queue that reviews changes is the one."""
    await service.set_policy(
        PRIMARY_ORG,
        FieldPolicy(path=f"{AUTONOMY_PATH}.rules", approval_gated=True),
        actor_id=ACTOR,
    )

    with pytest.raises(ChangeRequiresApproval):
        await service.set_settings(
            TEAM,
            {"policies": {"autonomy": {"rules": [a_rule("act_and_report")]}}},
            actor_id=ACTOR,
        )

    effective = await service.resolve(TEAM)
    assert policy_set_of(effective.config.policies).rules == ()


@pytest.mark.parametrize(
    ("patch", "path"),
    [
        ({"rules": [{"scope": {"kind": "galaxy"}, "level": "act_and_report"}]}, "kind"),
        ({"rules": [{"scope": {"kind": "resource"}, "level": "act_and_report"}]}, "scope"),
        ({"rules": [{"scope": {"kind": "deployment"}, "level": "run_wild"}]}, "level"),
        (
            {
                "rules": [
                    {
                        "scope": {"kind": "deployment"},
                        "level": "act_on_low_risk",
                        "risk_bound": "reckless",
                    }
                ]
            },
            "risk_bound",
        ),
        (
            {
                "freezes": [
                    {
                        "name": "backups",
                        "start": "1am",
                        "end": "04:00",
                        "scope": {"kind": "deployment"},
                    }
                ]
            },
            "start",
        ),
        (
            {
                "freezes": [
                    {
                        "name": "backups",
                        "start": "01:00",
                        "end": "04:00",
                        "timezone": "Mars/Olympus",
                        "scope": {"kind": "deployment"},
                    }
                ]
            },
            "timezone",
        ),
        ({"budgets": [{"name": "hourly", "counted_by": "vibes"}]}, "counted_by"),
        ({"budgets": [{"name": "hourly", "limit": -1}]}, "limit"),
        (
            {
                "overrides": [
                    {
                        "name": "maintenance",
                        "expires_at": "2026-03-12T14:00:00",
                        "scope": {"kind": "deployment"},
                        "level": "act_and_report",
                    }
                ]
            },
            "expires_at",
        ),
        ({"nonsense": True}, "nonsense"),
    ],
)
async def test_a_malformed_policy_is_refused_at_save_time_naming_the_field(
    service: ConfigService,
    four_levels: tuple[str, ...],
    patch: dict[str, Any],
    path: str,
) -> None:
    """Never at decision time: a refusal mid-incident about a typo is unusable."""
    with pytest.raises(ConfigInvalid) as refused:
        await service.set_settings(TEAM, {"policies": {"autonomy": patch}}, actor_id=ACTOR)
    assert path in str(refused.value)

    # And nothing reached storage, so no decision can ever read it.
    document = await service.document(TEAM)
    assert document.settings == {}


async def test_a_reviewed_document_can_be_imported_as_a_configuration_write(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    """Import goes through the write path, so it inherits the locks and the gate."""
    from datetime import time

    from platform.autonomy.bounds import BudgetRule, FreezeWindow
    from platform.autonomy.policy import PolicyRule

    posture = PolicySet(
        rules=(
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.LABELS, labels={"env": "lab"}),
                level=AutonomyLevel.ACT_ON_LOW_RISK,
                risk_bound=RiskClass.MODERATE,
            ),
        ),
        freezes=(
            FreezeWindow(
                name="backups",
                scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id="tank"),
                start=time(1, 0),
                end=time(4, 0),
                timezone="Europe/Lisbon",
            ),
        ),
        budgets=(BudgetRule(name="hourly", limit=3),),
    )

    await service.set_settings(
        TEAM, {"policies": {"autonomy": settings_of(posture)}}, actor_id=ACTOR
    )

    effective = await service.resolve(TEAM)
    read_back = policy_set_of(effective.config.policies)

    assert read_back.rules[0].scope.labels == {"env": "lab"}
    assert read_back.rules[0].risk_bound is RiskClass.MODERATE
    assert read_back.freezes[0].timezone == "Europe/Lisbon"
    assert read_back.budgets[0].limit == 3

    resolved = resolve(action(subjects=(subject(labels={"env": "lab"}),)), read_back, at=NOON)
    assert resolved.level is AutonomyLevel.ACT_ON_LOW_RISK


async def test_a_node_with_no_autonomy_configuration_resolves_to_propose_only(
    service: ConfigService, four_levels: tuple[str, ...]
) -> None:
    effective = await service.resolve(TEAM)
    policies = policy_set_of(effective.config.policies)
    assert policies == PolicySet()
    assert resolve(action(), policies, at=NOON).level is AutonomyLevel.PROPOSE_ONLY


async def test_the_write_is_audited_like_every_other_configuration_change(
    service: ConfigService,
    four_levels: tuple[str, ...],
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    await service.set_settings(
        TEAM,
        {"policies": {"autonomy": {"rules": [a_rule("act_and_report")]}}},
        actor_id=ACTOR,
    )
    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(resource_kind="config_node", limit=100)
    assert any(AUTONOMY_PATH in str(event.detail) for event in events)


async def test_a_direct_write_that_bypassed_validation_is_still_read_safely(
    gateway: PersistenceGateway, scope: TenantScope, service: ConfigService
) -> None:
    """Storage is not the only place a document can come from, so reading is total."""
    await write_node(gateway, scope, PRIMARY_ORG, parent_id=None)
    await write_node(
        gateway,
        scope,
        TEAM,
        parent_id=PRIMARY_ORG,
        settings={"policies": {"autonomy": {"rules": [a_rule("act_and_report")]}}},
    )
    effective = await service.resolve(TEAM)
    assert policy_set_of(effective.config.policies).rules[0].level is AutonomyLevel.ACT_AND_REPORT
