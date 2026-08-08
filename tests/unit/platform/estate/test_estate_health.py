"""Health, and the rule that every state on every kind can be explained.

The load-bearing assertion in this file is ``test_every_state_on_every_kind_is_
explainable``: it walks the whole closed set against every declared kind and
demands a retrievable derivation for each. A health model that cannot say why is
a status column with extra steps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.estate import MAX_HEALTH_SIGNALS
from platform.estate.health.derive import RULE_NO_SIGNALS, RULE_PROVIDER_STATUS, derive_from
from platform.estate.health.mapping import COMMON_STATUSES, DEFAULT_MAPPING, StatusMapping
from platform.estate.health.rollup import RULE_PREFIX, RollupRule, roll_up, rule_for
from platform.estate.kinds import (
    KIND_BACKUP_JOB,
    KIND_CLUSTER,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    core_registry,
)
from platform.estate.service import EstateService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EstateQuery,
    HealthDerivation,
    PersistenceGateway,
    Resource,
    ResourceHealth,
    TenantScope,
)

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def resource(
    resource_id: str = "r-1",
    *,
    kind: str = KIND_VIRTUAL_MACHINE,
    parent_id: str | None = None,
    health: ResourceHealth = ResourceHealth.HEALTHY,
    derived_at: datetime | None = None,
) -> Resource:
    """Return a resource carrying a derivation."""
    return Resource(
        resource_id=resource_id,
        kind=kind,
        source="proxmox",
        native_id=resource_id,
        display_name=resource_id,
        parent_id=parent_id,
        health=health,
        derivation=HealthDerivation(
            state=health,
            rule=RULE_PROVIDER_STATUS,
            derived_at=derived_at or at(),
            explanation=f"the provider reported {health.value}",
        ),
        first_seen_at=at(),
        last_seen_at=at(),
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return a store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


@pytest.fixture
def scope() -> TenantScope:
    """Return the tenant these tests read."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def service(gateway: PersistenceGateway) -> EstateService:
    """Return the estate service over the core kinds."""
    return EstateService(gateway=gateway, kinds=core_registry())


# --- Signals and the closed set -------------------------------------------------


def test_a_signal_records_its_name_its_value_and_when_it_was_seen() -> None:
    derivation = derive_from(
        raw_status="running",
        signals={"disk_fill_percent": "91"},
        at=at(),
        source="proxmox",
    )

    by_name = {signal.name: signal for signal in derivation.signals}
    assert by_name[RULE_PROVIDER_STATUS].value == "running"
    assert by_name["disk_fill_percent"].value == "91"
    assert by_name["disk_fill_percent"].observed_at == at()
    assert by_name["disk_fill_percent"].source == "proxmox"


def test_signals_are_bounded_so_a_derivation_stays_readable() -> None:
    derivation = derive_from(
        raw_status="running",
        signals={f"metric_{n}": str(n) for n in range(100)},
        at=at(),
    )

    assert len(derivation.signals) <= MAX_HEALTH_SIGNALS


def test_every_state_a_mapping_can_produce_is_in_the_closed_set() -> None:
    """T-022: there is no path to a state outside the seven."""
    produced = {DEFAULT_MAPPING.state_for(word) for word in COMMON_STATUSES}
    produced |= {DEFAULT_MAPPING.state_for(word) for word in ("", "  ", "invented-by-a-vendor")}

    assert produced <= set(ResourceHealth)


def test_an_unmapped_provider_status_becomes_unknown_and_never_healthy() -> None:
    """T-023, and the rule that costs the most and is worth the most."""
    derivation = derive_from(raw_status="reconfiguring", signals={}, at=at(), source="proxmox")

    assert derivation.state is ResourceHealth.UNKNOWN
    assert derivation.state is not ResourceHealth.HEALTHY
    # The raw value is retained, which is the only way a wrong mapping is
    # diagnosable at all.
    assert derivation.raw_status == "reconfiguring"
    assert "reconfiguring" in derivation.explanation
    assert "mapping" in derivation.explanation


def test_a_resource_with_no_status_and_no_signals_is_unknown() -> None:
    derivation = derive_from(raw_status="", signals={}, at=at(), source="proxmox")

    assert derivation.state is ResourceHealth.UNKNOWN
    assert derivation.rule == RULE_NO_SIGNALS
    assert "nobody said it was" in derivation.explanation


def test_a_declared_override_beats_the_shared_vocabulary() -> None:
    mapping = StatusMapping(source="odd-vendor", overrides={"active": ResourceHealth.DEGRADED})

    assert mapping.state_for("active") is ResourceHealth.DEGRADED
    assert mapping.state_for("ACTIVE") is ResourceHealth.DEGRADED
    assert DEFAULT_MAPPING.state_for("active") is ResourceHealth.HEALTHY


def test_a_paused_guest_is_maintenance_rather_than_a_fault() -> None:
    assert DEFAULT_MAPPING.state_for("paused") is ResourceHealth.MAINTENANCE
    assert not ResourceHealth.MAINTENANCE.is_problem


# --- Derivations are retrievable (SC-005) --------------------------------------


async def test_every_state_on_every_kind_is_explainable(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-005: for every kind × every state, a derivation comes back."""
    registry = core_registry()
    written: list[tuple[str, ResourceHealth]] = []

    async with gateway.begin(scope) as uow:
        for kind in registry.all():
            for state in ResourceHealth:
                resource_id = f"{kind.name}:{state.value}"
                await uow.estate.upsert(
                    Resource(
                        resource_id=resource_id,
                        kind=kind.name,
                        source="proxmox",
                        native_id=resource_id,
                        display_name=resource_id,
                        first_seen_at=at(),
                        last_seen_at=at(),
                    )
                )
                await uow.estate.record_health(
                    resource_id,
                    HealthDerivation(
                        state=state,
                        rule=RULE_PROVIDER_STATUS,
                        derived_at=at(),
                        raw_status=state.value,
                        explanation=f"the provider reported {state.value}",
                    ),
                )
                written.append((resource_id, state))

    for resource_id, state in written:
        detail = await service.detail(scope, resource_id, now=at())
        assert detail is not None, resource_id
        assert detail.view.derivation is not None, resource_id
        assert detail.view.explanation, resource_id
        assert detail.view.stored_health is state, resource_id
        assert detail.transitions, resource_id
        assert detail.transitions[0].state is state, resource_id


# --- Freshness (FR-016) ---------------------------------------------------------


async def test_an_observation_past_its_kinds_interval_reports_stale(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Acceptance scenario 9: stale rather than its last known state."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-vm", kind=KIND_VIRTUAL_MACHINE))

    fresh = await service.detail(scope, "r-vm", now=at(30))
    aged = await service.detail(scope, "r-vm", now=at(24 * 60))

    assert fresh is not None and aged is not None
    assert fresh.view.health is ResourceHealth.HEALTHY
    assert aged.view.health is ResourceHealth.STALE
    # The last known state is still readable; it is just not what is reported.
    assert aged.view.stored_health is ResourceHealth.HEALTHY
    assert "freshness interval" in aged.view.explanation


async def test_a_kind_with_a_longer_interval_is_still_fresh_when_a_shorter_one_is_not(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-vm", kind=KIND_VIRTUAL_MACHINE))
        await uow.estate.upsert(resource("r-backup", kind=KIND_BACKUP_JOB))

    guest = await service.detail(scope, "r-vm", now=at(24 * 60))
    backup = await service.detail(scope, "r-backup", now=at(24 * 60))

    assert guest is not None and backup is not None
    assert guest.view.health is ResourceHealth.STALE
    assert backup.view.health is ResourceHealth.HEALTHY
    assert backup.view.freshness_seconds > guest.view.freshness_seconds


# --- Rollup (FR-015) ------------------------------------------------------------


def test_the_rule_a_kind_uses_is_declared_and_conservative_by_default() -> None:
    assert rule_for(KIND_NODE) is RollupRule.MAJORITY_HEALTHY
    assert rule_for(KIND_BACKUP_JOB) is RollupRule.WORST_CHILD
    assert rule_for(KIND_VIRTUAL_MACHINE) is RollupRule.OWN_ONLY
    assert rule_for("a-kind-nobody-declared") is RollupRule.OWN_ONLY


def test_a_majority_of_failing_children_makes_the_parent_unhealthy() -> None:
    parent = resource("node", kind=KIND_NODE)
    children = [
        resource("g1", health=ResourceHealth.UNHEALTHY),
        resource("g2", health=ResourceHealth.UNHEALTHY),
        resource("g3", health=ResourceHealth.HEALTHY),
    ]

    derived = roll_up(parent, children, now=at())

    assert derived.state is ResourceHealth.UNHEALTHY
    assert derived.rule == f"{RULE_PREFIX}{RollupRule.MAJORITY_HEALTHY.value}"
    assert "2 of 3 children" in derived.explanation


def test_a_minority_of_failing_children_makes_the_parent_degraded() -> None:
    parent = resource("node", kind=KIND_NODE)
    children = [
        resource("g1", health=ResourceHealth.UNHEALTHY),
        resource("g2", health=ResourceHealth.HEALTHY),
        resource("g3", health=ResourceHealth.HEALTHY),
    ]

    assert roll_up(parent, children, now=at()).state is ResourceHealth.DEGRADED


def test_worst_child_makes_one_failure_the_parents_failure() -> None:
    parent = resource("job", kind=KIND_BACKUP_JOB)
    children = [resource("d1", health=ResourceHealth.UNHEALTHY), resource("d2")]

    derived = roll_up(parent, children, now=at())

    assert derived.state is ResourceHealth.UNHEALTHY
    assert derived.rule == f"{RULE_PREFIX}{RollupRule.WORST_CHILD.value}"


def test_a_child_in_maintenance_does_not_count_against_its_parent() -> None:
    """Planned work on one guest must not light up the node it runs on."""
    parent = resource("node", kind=KIND_NODE)
    paused = resource("g1", health=ResourceHealth.UNHEALTHY)
    paused = Resource(
        resource_id=paused.resource_id,
        kind=paused.kind,
        source=paused.source,
        native_id=paused.native_id,
        health=paused.health,
        derivation=paused.derivation,
        maintenance_until=at(60),
        maintenance_reason="firmware",
        last_seen_at=at(),
    )

    derived = roll_up(parent, [paused, resource("g2")], now=at(1))

    assert derived.state is ResourceHealth.HEALTHY
    assert "0 of 1 children" in derived.explanation


def test_a_parent_that_is_itself_down_stays_down_however_healthy_its_children_look() -> None:
    parent = resource("node", kind=KIND_NODE, health=ResourceHealth.UNHEALTHY)

    assert roll_up(parent, [resource("g1"), resource("g2")], now=at()).state is (
        ResourceHealth.UNHEALTHY
    )


def test_the_rule_is_visible_on_the_parent(
    service: EstateService,
) -> None:
    parent = resource("cluster", kind=KIND_CLUSTER)

    derived = roll_up(parent, [resource("n1", kind=KIND_NODE)], now=at())

    assert derived.rule.startswith(RULE_PREFIX)
    assert RollupRule.MAJORITY_HEALTHY.value in derived.rule


async def test_a_parents_health_accounts_for_its_children_when_it_is_read(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Acceptance scenario 5, end to end through the service."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("node", kind=KIND_NODE))
        for guest_id, state in (
            ("g1", ResourceHealth.UNHEALTHY),
            ("g2", ResourceHealth.UNHEALTHY),
            ("g3", ResourceHealth.HEALTHY),
        ):
            await uow.estate.upsert(resource(guest_id, parent_id="node", health=state))

    detail = await service.detail(scope, "node", now=at(1))

    assert detail is not None
    assert detail.view.health is ResourceHealth.UNHEALTHY
    assert detail.view.rollup_rule is RollupRule.MAJORITY_HEALTHY
    assert detail.view.derivation is not None
    assert detail.view.derivation.rule.startswith(RULE_PREFIX)
    assert len(detail.children) == 3


async def test_applying_rollups_stores_the_aggregate_so_a_health_query_finds_it(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("node", kind=KIND_NODE))
        await uow.estate.upsert(resource("g1", parent_id="node", health=ResourceHealth.UNHEALTHY))
        await uow.estate.upsert(resource("g2", parent_id="node", health=ResourceHealth.UNHEALTHY))

    updated = await service.apply_rollups(scope, now=at(1))

    assert updated == ("node",)
    async with gateway.begin(scope) as uow:
        unhealthy = await uow.estate.query(EstateQuery(health=(ResourceHealth.UNHEALTHY,)))
        history = await uow.estate.transitions("node")
    assert "node" in {found.resource_id for found in unhealthy}
    assert history[0].rule.startswith(RULE_PREFIX)


# --- Maintenance (FR-017) -------------------------------------------------------


async def test_maintenance_is_in_the_estate_and_out_of_the_problem_count(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-008."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-vm", health=ResourceHealth.UNHEALTHY))

    view = await service.enter_maintenance(
        scope, "r-vm", until=at(30), reason="firmware upgrade", at=at(1)
    )
    summary = await service.summarise(scope, now=at(2))

    assert view.health is ResourceHealth.MAINTENANCE
    assert summary.total == 1
    assert summary.maintenance == 1
    assert summary.problems == 0


async def test_leaving_maintenance_restores_the_state_and_records_both_ends(
    service: EstateService, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-vm", health=ResourceHealth.UNHEALTHY))

    await service.enter_maintenance(scope, "r-vm", until=at(30), reason="firmware", at=at(1))
    view = await service.leave_maintenance(scope, "r-vm", at=at(2))

    assert view.health is ResourceHealth.UNHEALTHY
    async with gateway.begin(scope) as uow:
        history = await uow.estate.transitions("r-vm")
    rules = {entry.rule for entry in history}
    assert "maintenance_window_opened" in rules
    assert "maintenance_window_closed" in rules
