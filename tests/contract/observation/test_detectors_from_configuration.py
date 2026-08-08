"""Contract: a team adds a detector by writing configuration, and inheritance applies.

Against the *real* configuration service rather than a stand-in, because the
claim FR-006 makes is about the hierarchy — a detector declared at the division
reaches the squad, a squad may add its own, and the schema refuses a field
nobody declared. A test against a hand-built settings object would prove that
the conversion works and nothing about whether a team can actually do this.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from platform.config_service.catalogue import StaticCatalogue, StaticIntegrationDirectory
from platform.config_service.errors import ConfigInvalid
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.observation.detectors import config as detector_config
from platform.observation.detectors.model import ConditionKind, GroupingKey
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)

pytestmark = pytest.mark.contract

ORG = "acme"
DIVISION = "division-platform"
TEAM = "team-payments"
ACTOR = "erik@example.test"


def a_detector(detector_id: str, **overrides: object) -> dict[str, object]:
    """Return the settings document one detector is written as."""
    return {
        "detector_id": detector_id,
        "signal": "storage.used_percent",
        "name": detector_id,
        "description": "A datastore that fills stops every guest on it at once.",
        "resource_kinds": ["datastore"],
        "fire_value": 90.0,
        "clear_value": 80.0,
        "for_seconds": 300,
        "recovery_seconds": 300,
        "severity": "critical",
        **overrides,
    }


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Yield an in-memory gateway with a three-level hierarchy."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        # The organisation's own root node is created with the organisation.
        for node_id, parent_id, kind in (
            (DIVISION, ORG, ConfigNodeKind.TEAM),
            (TEAM, DIVISION, ConfigNodeKind.TEAM),
        ):
            await uow.config.upsert(
                ConfigNode(node_id=node_id, kind=kind, name=node_id, parent_id=parent_id)
            )
    yield store
    await store.close()


@pytest.fixture
def service(gateway: PersistenceGateway) -> ConfigService:
    """Return the real configuration service over that hierarchy."""
    return ConfigService(
        gateway=gateway,
        scope=TenantScope(org_id=ORG),
        catalogue=StaticCatalogue.of([]),
        integrations=StaticIntegrationDirectory.of([]),
        guardrails=GuardrailEngine(),
    )


async def test_a_detector_written_at_a_division_reaches_the_team(
    service: ConfigService,
) -> None:
    """The whole of "a team can add one without new code", asserted end to end."""
    await service.set_settings(
        DIVISION,
        {"policies": {"observation": {"detectors": [a_detector("datastore-near-full")]}}},
        actor_id=ACTOR,
    )

    effective = await service.resolve(TEAM)
    resolved = detector_config.read(effective.config.policies.observation)

    assert [entry.detector_id for entry in resolved.detectors] == ["datastore-near-full"]
    assert resolved.detectors[0].condition.kind is ConditionKind.THRESHOLD
    assert resolved.detectors[0].grouping_key is GroupingKey.DETECTOR


async def test_a_team_may_declare_its_own_set(service: ConfigService) -> None:
    """A list replaces rather than merges, which is what the merge rules already say."""
    await service.set_settings(
        DIVISION,
        {"policies": {"observation": {"detectors": [a_detector("datastore-near-full")]}}},
        actor_id=ACTOR,
    )
    await service.set_settings(
        TEAM,
        {"policies": {"observation": {"detectors": [a_detector("guest-unreachable")]}}},
        actor_id=ACTOR,
    )

    effective = await service.resolve(TEAM)
    resolved = detector_config.read(effective.config.policies.observation)

    assert [entry.detector_id for entry in resolved.detectors] == ["guest-unreachable"]


async def test_a_field_nobody_declared_is_refused_at_the_write(
    service: ConfigService,
) -> None:
    """A typo stored, rendered, and never read is what a closed schema prevents."""
    with pytest.raises(ConfigInvalid):
        await service.set_settings(
            DIVISION,
            {"policies": {"observation": {"detectors": [a_detector("d", thershold=90.0)]}}},
            actor_id=ACTOR,
        )


async def test_a_pause_written_at_the_organisation_stops_every_team(
    service: ConfigService,
) -> None:
    """FR-021: detection stops and nothing is unconfigured."""
    await service.set_settings(
        ORG,
        {
            "policies": {
                "observation": {
                    "detectors": [a_detector("datastore-near-full")],
                    "paused": True,
                    "pause_reason": "migrating the cluster",
                }
            }
        },
        actor_id=ACTOR,
    )

    effective = await service.resolve(TEAM)
    resolved = detector_config.read(effective.config.policies.observation)

    assert resolved.enabled == ()
    assert len(resolved.detectors) == 1
    assert resolved.pause_reason == "migrating the cluster"
