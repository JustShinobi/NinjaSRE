"""Demo mode: one fictional deployment, labelled, coherent, and removable.

The dataset is feature 032's — the anonymised capture of a real deployment —
loaded into the real database rather than served over HTTP. That is the whole
design: two fictional deployments would drift, and the first person to notice
would be somebody whose demonstration looked nothing like the screenshots.
"""

from __future__ import annotations

import pytest

from config.constants.fixtures import DEMONSTRATION_LABEL_FIELD
from platform.estate.alert_resolution import UNRESOLVED_TARGET_PREFIX
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.estate_repository import EstateQuery, Resource
from platform.persistence.ports.incident_store import IncidentQuery
from platform.persistence.ports.transaction import TenantScope
from platform.startup.demo import (
    DemoRefused,
    demonstration_residue,
    is_demonstration,
    labelled,
    load_dataset,
    remove_demonstration,
    seed_demonstration,
    unresolved_references,
)
from tools.mockplane.seed import DEMONSTRATION_ORGANISATION

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id=DEMONSTRATION_ORGANISATION)


@pytest.fixture(scope="module")
def dataset() -> object:
    """Load the committed dataset once. It does not change between tests."""
    return load_dataset()


@pytest.fixture
def store() -> FakePersistence:
    return FakePersistence()


# --- The label ------------------------------------------------------------------


def test_labelling_stamps_the_field_the_sweep_looks_for() -> None:
    assert labelled({"a": 1})[DEMONSTRATION_LABEL_FIELD] is True


def test_an_unlabelled_mapping_is_not_demonstration_data() -> None:
    assert is_demonstration({"a": 1}) is False
    assert is_demonstration(labelled({"a": 1})) is True


def test_labelling_does_not_lose_what_was_there() -> None:
    assert labelled({"a": 1, "b": 2})["a"] == 1


# --- The dataset is coherent -----------------------------------------------------


def test_the_dataset_loads(dataset: object) -> None:
    assert dataset.guests  # type: ignore[attr-defined]
    assert dataset.runs  # type: ignore[attr-defined]
    assert dataset.incidents  # type: ignore[attr-defined]


def test_every_reference_in_the_dataset_resolves(dataset: object) -> None:
    """SC-007. A run must reference resources that exist, an episode must
    reference the run that produced it, a topology must connect resources that
    are related. Asserted over every reference rather than a sample."""
    assert unresolved_references(dataset) == ()


def test_an_unresolved_alert_target_is_a_subject_that_resolves_to_nothing_on_purpose(
    dataset: object,
) -> None:
    """The one subject the check above exempts, and the reason it has to.

    An alert that arrived for something this estate does not hold is recorded as
    a subject naming the target. Demanding that it resolve would be demanding
    the finding be about the very thing whose absence it reports — so the
    exemption is asserted here rather than left as a quiet ``continue``.
    """
    subjects = [
        str(subject)
        for incident in dataset.incidents  # type: ignore[attr-defined]
        for subject in incident.get("subjects", ())
    ]
    unresolved = [name for name in subjects if name.startswith(UNRESOLVED_TARGET_PREFIX)]

    assert unresolved, "the dataset no longer carries the case this exemption exists for"
    assert unresolved_references(dataset) == ()


# --- Seeding ----------------------------------------------------------------------


async def test_seeding_populates_the_estate_the_incidents_and_the_runs(
    store: FakePersistence, dataset: object
) -> None:
    report = await seed_demonstration(store, dataset=dataset)

    assert report.counts["resources"] > 50
    assert report.counts["incidents"] > 0
    assert report.counts["runs"] > 0
    assert report.counts["episodes"] > 0
    assert report.counts["approvals"] > 0
    assert report.counts["topology_nodes"] > 0
    assert report.counts["turns"] > 0


async def test_the_seeded_estate_is_readable_through_the_ordinary_port(
    store: FakePersistence, dataset: object
) -> None:
    """Loaded into the real database, not into a side channel: a console reading
    the estate the ordinary way sees it."""
    await seed_demonstration(store, dataset=dataset)

    async with store.begin(SCOPE) as uow:
        resources = await uow.estate.query(EstateQuery(limit=200))
        incidents = await uow.incidents.query(IncidentQuery(limit=50))

    assert len(resources) > 50
    assert incidents


async def test_every_seeded_record_carrying_a_metadata_column_is_labelled_in_it(
    store: FakePersistence, dataset: object
) -> None:
    """FR-017's first half. Asserted per record, across every kind that has a
    place to hold it, rather than on a sample."""
    await seed_demonstration(store, dataset=dataset)

    async with store.begin(SCOPE) as uow:
        for resource in await uow.estate.query(EstateQuery(limit=500)):
            assert is_demonstration(resource.attributes), resource.resource_id
        for run in await uow.run_traces.list_runs(limit=50):
            assert is_demonstration(run.metadata), run.run_id
        for episode in await uow.episodes.list_recent(limit=50):
            assert is_demonstration(episode.metadata), episode.episode_id
        for approval in await uow.approvals.list_pending(limit=50):
            assert is_demonstration(approval.arguments), approval.approval_id


async def test_every_seeded_record_without_one_is_labelled_by_its_tenant(
    store: FakePersistence, dataset: object
) -> None:
    """FR-017's second half, and the label that cannot be forgotten.

    ``org_id`` is on every row of every table in this schema, so a record kind
    added later is labelled by construction rather than by whoever writes its
    seeder remembering to stamp it. An incident has no metadata column; it is
    still unambiguously demonstration data, because it is in the demonstration
    tenant and nothing else is.
    """
    await seed_demonstration(store, dataset=dataset)

    async with store.begin(SCOPE) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=100))
    assert incidents

    async with store.begin_system() as system:
        organisations = {org.org_id for org in await system.orgs.list_organisations()}
    assert organisations == {DEMONSTRATION_ORGANISATION}


async def test_seeding_is_idempotent(store: FakePersistence, dataset: object) -> None:
    first = await seed_demonstration(store, dataset=dataset)
    second = await seed_demonstration(store, dataset=dataset, force=True)

    assert second.counts == first.counts
    async with store.begin(SCOPE) as uow:
        resources = await uow.estate.query(EstateQuery(limit=500))
    assert len(resources) == first.counts["resources"]


# --- Refusing to seed over real data ------------------------------------------------


async def test_demo_mode_refuses_a_deployment_that_already_holds_real_data(
    store: FakePersistence, dataset: object
) -> None:
    """FR-020. The one thing worse than an empty console is one where a real
    incident and a fictional one are side by side."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation(DEMONSTRATION_ORGANISATION, "Northwind")
    async with store.begin(SCOPE) as uow:
        await uow.estate.upsert(
            Resource(resource_id="real-1", kind="node", source="proxmox", native_id="real-1")
        )

    with pytest.raises(DemoRefused) as refusal:
        await seed_demonstration(store, dataset=dataset)

    assert "real-1" in str(refusal.value) or "1 record" in str(refusal.value)
    assert "--force" in str(refusal.value)


async def test_demo_mode_seeds_over_real_data_when_it_is_forced(
    store: FakePersistence, dataset: object
) -> None:
    async with store.begin_system() as system:
        await system.orgs.create_organisation(DEMONSTRATION_ORGANISATION, "Northwind")
    async with store.begin(SCOPE) as uow:
        await uow.estate.upsert(
            Resource(resource_id="real-1", kind="node", source="proxmox", native_id="real-1")
        )

    report = await seed_demonstration(store, dataset=dataset, force=True)

    assert report.forced is True


async def test_seeding_over_its_own_demonstration_data_is_not_a_refusal(
    store: FakePersistence, dataset: object
) -> None:
    """Re-seeding a demonstration is an ordinary thing to do and must not need a
    flag that also lets somebody seed over production."""
    await seed_demonstration(store, dataset=dataset)

    report = await seed_demonstration(store, dataset=dataset)

    assert report.forced is False


# --- Removal ---------------------------------------------------------------------


async def test_removal_leaves_nothing(store: FakePersistence, dataset: object) -> None:
    """SC-009, asserted by a full-table sweep rather than by spot checks."""
    await seed_demonstration(store, dataset=dataset)

    await remove_demonstration(store)

    assert await demonstration_residue(store) == ()


async def test_removal_reports_what_it_removed(store: FakePersistence, dataset: object) -> None:
    seeded = await seed_demonstration(store, dataset=dataset)

    removal = await remove_demonstration(store)

    assert removal.removed is True
    assert removal.counts["resources"] == seeded.counts["resources"]


async def test_removing_when_nothing_was_seeded_is_not_an_error(
    store: FakePersistence,
) -> None:
    removal = await remove_demonstration(store)

    assert removal.removed is False


async def test_removal_does_not_touch_another_organisation(
    store: FakePersistence, dataset: object
) -> None:
    """The demonstration lives in its own tenant. Removing it removes that
    tenant, which is exactly why it has to be its own."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.estate.upsert(
            Resource(resource_id="real-1", kind="node", source="k8s", native_id="real-1")
        )
    await seed_demonstration(store, dataset=dataset)

    await remove_demonstration(store)

    async with store.begin(TenantScope(org_id="acme")) as uow:
        survivors = await uow.estate.query(EstateQuery(limit=10))
    assert [resource.resource_id for resource in survivors] == ["real-1"]


async def test_the_sweep_would_notice_a_record_that_survived(
    store: FakePersistence, dataset: object
) -> None:
    """A sweep that always returns nothing proves nothing. This is the test that
    the sweep can see."""
    await seed_demonstration(store, dataset=dataset)

    residue = await demonstration_residue(store)

    assert residue, "the sweep found no demonstration data in a freshly seeded store"
