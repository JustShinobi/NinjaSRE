"""Reading the operator's own inventory, and refusing the parts that are not one.

The repository this reads is the answer to a question the hypervisor API cannot
be asked: which of these fifty-seven containers matters. Criticality, tier and
the domain a workload answers on are decisions somebody made and wrote down.

Three properties are worth holding, and the third is the one that would be
quietly lost first.

**A document that is not one is refused naming every problem at once.** An
operator fixing an inventory wants one pass through the file, not a loader that
reports the second mistake after the first is corrected.

**Nothing from the repository is executed and nothing outside it is read.** The
ingestion takes a document reader and asks it for five names. There is no path
by which a file in the tree makes this process run anything, and a reader is
what makes "a directory here" and "a raw URL there" one seam rather than two
code paths.

**A value shaped like a credential never lands.** Somebody's inventory will one
day carry a token in a description field, and the moment to catch it is before
it is stored rather than in a migration afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.estate import MAX_ENRICHMENT_DOCUMENT_BYTES, MAX_ENRICHMENT_ENTRIES
from integrations.proxmox.enrichment import (
    INVENTORY_DOCUMENTS,
    DirectoryInventory,
    InventoryTooLarge,
    domains_of,
    ingest,
    schema_for_document,
)
from integrations.proxmox.inventory import InventoryInvalid
from platform.estate.enrichment import DivergenceKind

pytestmark = pytest.mark.unit

CLUSTER = "HAL9000"

ZONES = """
zones:
  - name: mgmt
    cidr: 10.20.10.0/24
    gateway: 10.20.10.1
  - name: infra
    cidr: 10.20.20.0/24
    gateway: 10.20.20.1
  - name: apps
    cidr: 10.20.30.0/24
    gateway: 10.20.30.1
"""

NODES = """
nodes:
  - name: pve01
    criticality: high
    tier: hypervisor
    owner: ops
"""

CTS = """
containers:
  - vmid: 100
    name: plex
    node: pve02
    criticality: high
    tier: media
    owner: ops
  - vmid: 101
    name: paperless
    node: pve01
    criticality: medium
"""

VMS = """
virtual_machines:
  - vmid: 200
    name: builder
    node: pve01
    criticality: low
    tier: ci
"""

SERVICES = """
services:
  - name: plex
    domain: plex.example.internal
    vmid: 100
"""

DOCUMENTS = {
    "zones": ZONES,
    "nodes": NODES,
    "cts": CTS,
    "vms": VMS,
    "services": SERVICES,
}


def _tree(root: Path, documents: dict[str, str] | None = None) -> DirectoryInventory:
    """Write an inventory tree shaped like the repository's and return a reader."""
    written = DOCUMENTS if documents is None else documents
    cluster = root / "inventory" / "cluster"
    cluster.mkdir(parents=True)
    for name, body in written.items():
        (cluster / f"{name}.yaml").write_text(body, encoding="utf-8")
    return DirectoryInventory(root=root)


# --- what a good tree produces ------------------------------------------------


def test_the_zone_map_comes_out_of_the_declared_networks(tmp_path: Path) -> None:
    plan = ingest(_tree(tmp_path), cluster=CLUSTER)

    assert plan.zones.zone_for("10.20.30.7") == "apps"
    assert plan.zones.zone_for("10.20.20.4") == "infra"
    assert len(plan.zones.networks) == 3


def test_criticality_and_tier_are_keyed_by_the_vmid_both_sides_chose(tmp_path: Path) -> None:
    plan = ingest(_tree(tmp_path), cluster=CLUSTER)
    annotations = plan.by_key()

    assert annotations[f"{CLUSTER}/lxc/100"]["criticality"] == "high"
    assert annotations[f"{CLUSTER}/lxc/100"]["tier"] == "media"
    assert annotations[f"{CLUSTER}/qemu/200"]["tier"] == "ci"


def test_a_container_declaring_only_criticality_carries_only_that(tmp_path: Path) -> None:
    plan = ingest(_tree(tmp_path), cluster=CLUSTER)

    declared = plan.by_key()[f"{CLUSTER}/lxc/101"]
    assert declared["criticality"] == "medium"
    assert "tier" not in declared
    assert "owner" not in declared


def test_a_node_is_annotated_under_the_name_the_cluster_reports(tmp_path: Path) -> None:
    plan = ingest(_tree(tmp_path), cluster=CLUSTER)

    assert plan.by_key()["pve01"]["criticality"] == "high"


def test_the_traefik_domain_lands_on_the_workload_that_serves_it(tmp_path: Path) -> None:
    """The edge feature 055 resolves a blackbox alert through."""
    plan = ingest(_tree(tmp_path), cluster=CLUSTER)

    assert plan.by_key()[f"{CLUSTER}/lxc/100"]["domain"] == "plex.example.internal"
    assert domains_of(plan) == (
        {"domain": "plex.example.internal", "workload": f"{CLUSTER}/lxc/100"},
    )


def test_a_service_naming_a_guest_nothing_declares_is_a_divergence(tmp_path: Path) -> None:
    documents = dict(DOCUMENTS)
    documents["services"] = "services:\n  - name: ghost\n    domain: g.example\n    vmid: 999\n"

    plan = ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    only_in_file = [
        entry for entry in plan.divergences if entry.kind is DivergenceKind.ONLY_IN_FILE
    ]
    assert [entry.subject for entry in only_in_file] == [f"{CLUSTER}/lxc/999"]
    assert "g.example" in only_in_file[0].detail


def test_a_missing_document_is_read_as_declaring_nothing(tmp_path: Path) -> None:
    """An operator with no ``vms.yaml`` has no virtual machines, which is a
    statement rather than a failure. A missing ``zones.yaml`` is different and
    is covered below."""
    documents = {name: body for name, body in DOCUMENTS.items() if name != "vms"}

    plan = ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    assert f"{CLUSTER}/qemu/200" not in plan.by_key()
    assert f"{CLUSTER}/lxc/100" in plan.by_key()


# --- what is refused ----------------------------------------------------------


def test_a_document_the_schema_rejects_names_every_problem_at_once(tmp_path: Path) -> None:
    documents = dict(DOCUMENTS)
    documents["cts"] = (
        "containers:\n"
        "  - vmid: 'one hundred'\n"
        "    name: plex\n"
        "  - name: nameless\n"
        "  - vmid: 102\n"
        "    hair_colour: red\n"
    )

    with pytest.raises(InventoryInvalid) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    problems = refused.value.problems
    assert len(problems) == 3
    joined = "; ".join(problems)
    assert "cts.yaml" in joined
    assert "containers[0].vmid" in joined
    assert "containers[1]" in joined
    assert "hair_colour" in joined


def test_an_overlapping_pair_of_zones_is_refused_naming_both(tmp_path: Path) -> None:
    documents = dict(DOCUMENTS)
    documents["zones"] = (
        "zones:\n"
        "  - name: everything\n    cidr: 10.20.0.0/16\n"
        "  - name: apps\n    cidr: 10.20.30.0/24\n"
    )

    with pytest.raises(InventoryInvalid) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    joined = "; ".join(refused.value.problems)
    assert "10.20.0.0/16" in joined
    assert "10.20.30.0/24" in joined


def test_a_document_that_is_not_a_mapping_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    documents = dict(DOCUMENTS)
    documents["nodes"] = "- pve01\n- pve02\n"

    with pytest.raises(InventoryInvalid) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    assert any("nodes.yaml" in problem for problem in refused.value.problems)


def test_a_document_larger_than_the_bound_is_refused_before_it_is_parsed(
    tmp_path: Path,
) -> None:
    documents = dict(DOCUMENTS)
    documents["cts"] = "# " + "x" * MAX_ENRICHMENT_DOCUMENT_BYTES + "\ncontainers: []\n"

    with pytest.raises(InventoryTooLarge) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    assert "cts.yaml" in str(refused.value)
    assert str(MAX_ENRICHMENT_DOCUMENT_BYTES) in str(refused.value)


def test_more_entries_than_the_bound_allows_are_refused(tmp_path: Path) -> None:
    documents = dict(DOCUMENTS)
    documents["cts"] = "containers:\n" + "".join(
        f"  - vmid: {100 + index}\n" for index in range(MAX_ENRICHMENT_ENTRIES + 1)
    )

    with pytest.raises(InventoryTooLarge) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    assert str(MAX_ENRICHMENT_ENTRIES) in str(refused.value)


def test_a_value_shaped_like_a_credential_is_refused_naming_the_file_not_the_value(
    tmp_path: Path,
) -> None:
    """T-008. The file is named, the field is named, and the value is not."""
    secret = "ghp_0123456789abcdefghijklmnopqrstuvwxyzAB"
    documents = dict(DOCUMENTS)
    documents["cts"] = f"containers:\n  - vmid: 100\n    owner: {secret}\n"

    with pytest.raises(InventoryInvalid) as refused:
        ingest(_tree(tmp_path, documents), cluster=CLUSTER)

    joined = "; ".join(refused.value.problems)
    assert "cts.yaml" in joined
    assert "containers[0].owner" in joined
    assert secret not in joined
    assert secret not in str(refused.value)


def test_a_reader_pointed_at_nothing_says_so_rather_than_ingesting_an_empty_estate(
    tmp_path: Path,
) -> None:
    """A wrong path must not read as "this cluster has no zones", which would
    place every guest nowhere and report fifty-seven divergences."""
    with pytest.raises(InventoryInvalid) as refused:
        ingest(DirectoryInventory(root=tmp_path / "nowhere"), cluster=CLUSTER)

    assert any("zones.yaml" in problem for problem in refused.value.problems)


# --- the bundled schemas ------------------------------------------------------


def test_every_document_the_ingestion_reads_has_a_bundled_schema() -> None:
    for name, _ in INVENTORY_DOCUMENTS:
        schema = schema_for_document(name)
        assert schema["type"] == "object"
        assert schema["required"]


def test_no_bundled_schema_uses_a_keyword_the_validator_ignores() -> None:
    """The guard on a subset validator. A schema that grew ``oneOf`` would
    otherwise be *checked less* than it says, which is worse than not checking:
    the document would pass and the guarantee would be gone."""
    from integrations.proxmox.enrichment import SUPPORTED_KEYWORDS

    def walk(node: object, where: str) -> list[str]:
        if isinstance(node, dict):
            unsupported = [f"{where}.{key}" for key in node if key not in SUPPORTED_KEYWORDS]
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    unsupported.extend(
                        problem
                        for name, child in value.items()
                        for problem in walk(child, f"{where}.properties.{name}")
                    )
                elif key == "items":
                    unsupported.extend(walk(value, f"{where}.items"))
            return unsupported
        return []

    for name, _ in INVENTORY_DOCUMENTS:
        assert walk(schema_for_document(name), name) == []
