"""Reading the operator's declared inventory, which nothing ever did.

``integrations/proxmox/enrichment.py`` reads five YAML documents from a
repository the operator maintains by hand, validates each against a bundled
schema, screens every value for credential shapes, detects disagreements with
what the cluster reports, and returns an ``EnrichmentPlan``. It is tested,
documented, and has no production caller: ``ingest`` and ``DirectoryInventory``
appear only in their own module and their own tests, and
``TopologyDiscoveryRunner.plans`` is never passed.

So every estate in every deployment carried no criticality, no tier, no domain
and no owner — the four annotations the whole ingestion exists to produce, and
the ones a screen that ranks resources by importance needs. The zone survived
only because it is derived separately from an address.

**The path is a Proxmox option, not a new top-level setting.** Which repository
declares a cluster is a fact about that cluster, and the integration entry
already carries the vendor's own options.

**An unreadable inventory does not stop the sweep.** A deployment whose
repository moved should keep discovering its estate and lose the annotations,
because the alternative is an empty estate — and the annotations are the half
somebody can fix at leisure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway.http.enrichment_plans import compose_enrichment_plans, inventory_path_of

pytestmark = pytest.mark.unit

ZONES = """
version: 1
zones:
- name: apps
  cidr: 192.0.2.0/24
- name: dmz
  cidr: 198.51.100.0/24
"""

#: Written the way an operator's own inventory writes it: `id` rather than the
#: API's `vmid`, `hostname` rather than `name`, and operational fields beside
#: them that the ingestion never reads.
CONTAINERS = """
version: 1
containers:
- id: 101
  node: pve01
  hostname: medusa
  status: running
  zone: apps
  criticality: medium
"""


def _repository(root: Path) -> Path:
    directory = root / "inventory" / "cluster"
    directory.mkdir(parents=True)
    (directory / "zones.yaml").write_text(ZONES, encoding="utf-8")
    (directory / "cts.yaml").write_text(CONTAINERS, encoding="utf-8")
    return root


def test_the_path_is_read_from_the_integrations_own_options() -> None:
    assert inventory_path_of({"options": {"inventory_path": "/srv/infra"}}) == "/srv/infra"


def test_an_entry_declaring_no_inventory_reads_none() -> None:
    """The ordinary state of a deployment whose operator keeps no such repository."""
    assert inventory_path_of({"options": {}}) == ""
    assert inventory_path_of({}) == ""


async def test_a_declared_inventory_becomes_a_plan_the_sweep_can_apply(tmp_path: Path) -> None:
    plans = await compose_enrichment_plans(
        ({"name": "proxmox", "options": {"inventory_path": str(_repository(tmp_path))}},),
        cluster="pve",
    )

    assert "proxmox" in plans
    # The annotation the whole ingestion exists to produce, and the one no
    # deployment has ever carried.
    assert any(
        annotation.values.get("criticality") == "medium"
        for annotation in plans["proxmox"].annotations
    )


async def test_a_deployment_that_declared_no_inventory_composes_no_plan(tmp_path: Path) -> None:
    del tmp_path
    assert (
        await compose_enrichment_plans(({"name": "proxmox", "options": {}},), cluster="pve") == {}
    )


async def test_an_unreadable_inventory_loses_the_annotations_not_the_sweep(
    tmp_path: Path,
) -> None:
    """An empty estate is a worse failure than an unannotated one, and only one
    of them can be fixed at leisure."""
    plans = await compose_enrichment_plans(
        ({"name": "proxmox", "options": {"inventory_path": str(tmp_path / "nowhere")}},),
        cluster="pve",
    )

    assert plans == {}


async def test_an_invalid_inventory_is_refused_without_taking_the_boot_with_it(
    tmp_path: Path,
) -> None:
    """A document that fails its schema is the operator's to fix; a gateway that
    would not start is nobody's."""
    directory = tmp_path / "inventory" / "cluster"
    directory.mkdir(parents=True)
    (directory / "zones.yaml").write_text("version: 1\nzones: [{name: a}]\n", encoding="utf-8")

    plans = await compose_enrichment_plans(
        ({"name": "proxmox", "options": {"inventory_path": str(tmp_path)}},), cluster="pve"
    )

    assert plans == {}


def test_the_sweep_runner_is_handed_the_plans() -> None:
    """The joint. The ingestion has been correct and uncalled the whole time, and
    a test of compose_enrichment_plans alone would pass with nobody using it."""
    import inspect

    from gateway.http import scheduled_work

    assert "plans=" in inspect.getsource(scheduled_work.dispatcher_for)
