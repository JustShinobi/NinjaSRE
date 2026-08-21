"""Phases 7 and 8: the estate this integration populates, and how it is proved.

Discovery is where a hypervisor earns its place: one provider already knows the
whole shape — a cluster, its nodes, the guests on them, the datastores under
them — so the parentage does not have to be inferred from names.

The assertions that carry the most:

**Identity survives a rename and a migration and does not survive a reuse.** A
guest's identity holds the cluster, the kind, the VMID and *when it was created*.
Renaming changes none of them; migrating changes only the parent; destroying
guest 100 and creating a new one with the same number changes the creation time,
which is what stops six months of the old guest's history attaching itself to a
guest that has nothing to do with it.

**A node that is down leaves stale guests, not absent ones.** The cluster-wide
resource list still carries them. A sweep that dropped them would let a complete
full sweep conclude they had been deleted, and the estate would decommission
every guest on a node that was rebooting.

**A cloud-init password never reaches storage.** Guest configuration routinely
carries one. The masking is the existing ruleset, applied before the attribute is
attached, and the test looks for the value rather than for the call.

**A reading nobody publishes is unavailable, not healthy.** Failed systemd units,
bridge state and thin-pool metadata are not in the Proxmox API at all, and this
client is forbidden from getting a shell to find them. Reporting them as fine
would be the exact failure this wave exists to prevent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from integrations._base.retry import RetryPolicy
from integrations._base.transport import RequestContext
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import (
    KIND_PHYSICAL_DISK,
    KIND_REPLICATION_JOB,
    KIND_STORAGE_POOL,
    PROXMOX_KINDS,
    ProxmoxDiscovery,
)
from integrations.proxmox.health import PROXMOX_STATUS_MAPPING
from integrations.proxmox.identity import creation_time, guest_identity
from integrations.proxmox.inventory import (
    Inventory,
    InventoryInvalid,
    InventorySource,
    divergences,
)
from integrations.proxmox.privileges import (
    READ_PRIVILEGES,
    WRITE_PRIVILEGES,
    privilege_report,
)
from integrations.proxmox.redaction import masked_configuration
from integrations.proxmox.schema import API_BASE
from integrations.proxmox.supplementary import (
    SUPPLEMENTARY_PUBLISHER,
    supplementary_readings,
)
from integrations.proxmox.verifier import ProxmoxVerifier
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.estate.discovery.port import DiscoveryMode, SweepBudget
from platform.estate.kinds import (
    KIND_BACKUP_JOB,
    KIND_CLUSTER,
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    core_registry,
)
from platform.persistence.ports.estate_repository import ResourceHealth
from tests.support.proxmox import (
    PRIMARY,
    SECONDARY,
    ClusterState,
    RecordedCluster,
    recorded,
)

pytestmark = pytest.mark.unit

CONTEXT = RequestContext(org_id="acme", team_id="homelab", capability="proxmox_discovery")
NO_RETRY = RetryPolicy(max_attempts=1)
PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "integrations" / "proxmox"


@dataclass(slots=True)
class RecordedTransport:
    """The recorded cluster, behind the proxy transport protocol."""

    cluster: RecordedCluster
    calls: list[str] = field(default_factory=list)

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Answer ``request`` from the recording, or with Proxmox's node-down status."""
        path = urlsplit(request.url).path.removeprefix(API_BASE)
        self.calls.append(path)
        try:
            payload = self.cluster.payload(path)
        except KeyError:
            return OutboundResponse(595, {}, b"595 no route to host")
        return OutboundResponse(
            200,
            {"content-type": "application/json"},
            json.dumps({"data": payload}).encode("utf-8"),
        )


def source_for(
    state: ClusterState = ClusterState.HEALTHY,
) -> tuple[ProxmoxDiscovery, RecordedTransport]:
    """Return a discovery source reading ``state``, and the transport behind it."""
    transport = RecordedTransport(cluster=recorded(state))
    client = ProxmoxClient(transport=transport, context=CONTEXT, retry=NO_RETRY)
    return ProxmoxDiscovery(client=client), transport


async def sweep(
    state: ClusterState = ClusterState.HEALTHY,
    *,
    budget: SweepBudget | None = None,
) -> tuple[Any, RecordedTransport]:
    """Return one full sweep of ``state`` and the transport that served it."""
    source, transport = source_for(state)
    page = await source.discover(mode=DiscoveryMode.FULL, budget=budget or SweepBudget())
    return page, transport


# --- T-029: every declared kind ----------------------------------------------


def test_the_declaration_names_every_kind_this_integration_emits() -> None:
    source, _ = source_for()

    declared = set(source.declaration.kinds)

    assert declared == {
        KIND_CLUSTER,
        KIND_NODE,
        KIND_VIRTUAL_MACHINE,
        KIND_CONTAINER,
        KIND_DATASTORE,
        KIND_STORAGE_POOL,
        KIND_BACKUP_JOB,
        KIND_REPLICATION_JOB,
        KIND_PHYSICAL_DISK,
    }


def test_the_kinds_this_integration_adds_register_onto_the_core_set() -> None:
    """FR-002's extensibility half: an integration extends without editing the core."""
    registry = core_registry()

    for kind in PROXMOX_KINDS:
        registry.register(kind)

    assert {KIND_STORAGE_POOL, KIND_REPLICATION_JOB, KIND_PHYSICAL_DISK} <= set(registry.names())


def test_discovery_is_declared_read_only() -> None:
    """SC-008, and the declaration refuses to be anything else."""
    from core.capability.metadata import SideEffectLevel

    source, _ = source_for()

    assert source.declaration.side_effect_level is SideEffectLevel.READ


async def test_a_sweep_produces_every_declared_kind_with_its_parent() -> None:
    page, _ = await sweep()

    by_kind: dict[str, list[Any]] = {}
    for resource in page.resources:
        by_kind.setdefault(resource.kind, []).append(resource)

    assert set(by_kind) == set(ProxmoxDiscovery(client=None).declaration.kinds) - {
        KIND_REPLICATION_JOB
    }, "the reference cluster has no replication jobs, which is the finding"
    assert page.complete

    cluster = by_kind[KIND_CLUSTER][0]
    assert cluster.parent_native_id == ""
    for node in by_kind[KIND_NODE]:
        assert node.parent_native_id == cluster.native_id
    for container in by_kind[KIND_CONTAINER]:
        assert container.parent_native_id.startswith("node/")


async def test_every_guest_carries_the_identifier_its_host_side_series_are_keyed_by() -> None:
    """The one attribute a container's resource usage cannot be looked up without.

    Read from a declared attribute rather than split back out of the correlation
    key, because a query built from a parsed string returns nothing the day the
    format changes — and nothing is what a container under no pressure looks
    like.
    """
    page, _ = await sweep()

    guests = [
        resource
        for resource in page.resources
        if resource.kind in {KIND_CONTAINER, KIND_VIRTUAL_MACHINE}
    ]
    assert guests
    for guest in guests:
        vmid = guest.attributes.get("vmid")
        assert isinstance(vmid, int) and vmid > 0, f"{guest.native_id} carries no vmid"
        assert guest.correlation_key.endswith(f"/{vmid}")


async def test_the_cluster_carries_quorum_as_an_attribute_and_a_signal() -> None:
    page, _ = await sweep()

    cluster = next(found for found in page.resources if found.kind == KIND_CLUSTER)

    assert cluster.attributes["quorate"] is True
    assert cluster.attributes["node_count"] == 2
    assert cluster.signals["quorum_margin"] == "0"


async def test_datastores_hang_from_the_node_that_can_see_them() -> None:
    page, _ = await sweep()

    datastores = [found for found in page.resources if found.kind == KIND_DATASTORE]

    assert datastores
    assert all(found.parent_native_id.startswith("node/") for found in datastores)


async def test_a_datastore_visible_from_one_node_and_not_another_is_two_records() -> None:
    """Shared storage seen by two nodes is two observations of the same store."""
    page, _ = await sweep()

    names = [found.display_name for found in page.resources if found.kind == KIND_DATASTORE]

    assert names.count("local-lvm") == 2
    identifiers = {found.native_id for found in page.resources if found.display_name == "local-lvm"}
    assert len(identifiers) == 2, "two nodes' views are two resources, not one overwritten"


async def test_a_backup_job_records_what_it_covers_and_whether_it_is_on() -> None:
    page, _ = await sweep()

    jobs = {found.display_name: found for found in page.resources if found.kind == KIND_BACKUP_JOB}

    assert jobs["pve01 baseline"].attributes["enabled"] is False
    assert jobs["pve01 baseline"].signals["covers"] == "every guest"


async def test_thin_pools_are_storage_pools_with_both_percentages() -> None:
    page, _ = await sweep()

    pools = {
        found.display_name: found for found in page.resources if found.kind == KIND_STORAGE_POOL
    }

    assert pools["data-pool"].signals["data_percent"] == "72.38"
    assert pools["data-pool"].signals["metadata_percent"] == "31.98"


async def test_a_physical_disk_carries_its_smart_verdict() -> None:
    page, _ = await sweep()

    disks = [found for found in page.resources if found.kind == KIND_PHYSICAL_DISK]

    assert disks
    assert all(found.provider_status for found in disks)


# --- T-030 and T-031: identity ------------------------------------------------


def test_identity_survives_a_rename() -> None:
    before = guest_identity("HAL9000", "lxc", 100, created_at="1700000000")
    after = guest_identity("HAL9000", "lxc", 100, created_at="1700000000")

    assert before == after


def test_identity_survives_a_migration_between_nodes() -> None:
    """The node is the parent, not part of the identity."""
    identity = guest_identity("HAL9000", "lxc", 100, created_at="1700000000")

    assert PRIMARY not in identity
    assert SECONDARY not in identity


def test_a_reused_vmid_produces_a_distinct_resource_rather_than_a_resurrection() -> None:
    original = guest_identity("HAL9000", "lxc", 100, created_at="1700000000")
    replacement = guest_identity("HAL9000", "lxc", 100, created_at="1754800000")

    assert original != replacement


def test_a_creation_time_is_read_from_the_configurations_own_metadata() -> None:
    found = creation_time({"meta": "creation-lxc=9.2.6,ctime=1754800000"})

    assert found == "1754800000"


def test_a_configuration_with_no_creation_metadata_says_so_rather_than_inventing_one() -> None:
    """An invented discriminator would make every sweep produce a new resource."""
    assert creation_time({"hostname": "plex"}) == ""


async def test_a_guest_without_a_creation_time_is_still_identified_and_flagged() -> None:
    source, transport = source_for()
    transport.cluster.responses[f"/nodes/{SECONDARY}/lxc/100/config"] = {"hostname": "plex"}

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())

    guest = next(found for found in page.resources if found.native_id.endswith("/100"))
    assert guest.signals["identity_discriminator"] == "unavailable"


# --- T-032: relationships -----------------------------------------------------


async def test_a_backup_job_records_the_guests_it_covers() -> None:
    page, _ = await sweep()

    job = next(
        found
        for found in page.resources
        if found.kind == KIND_BACKUP_JOB and found.display_name == "pve02 baseline"
    )

    assert job.signals["covered_vmids"] == "100,115,140,142,161"


async def test_a_replication_job_records_both_ends() -> None:
    source, transport = source_for()
    transport.cluster.responses[f"/nodes/{SECONDARY}/replication"] = [
        {
            "id": "100-0",
            "source": SECONDARY,
            "target": PRIMARY,
            "guest": 100,
            "last_sync": 1_754_800_000,
            "duration": 12.5,
            "fail_count": 0,
        }
    ]

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())

    job = next(found for found in page.resources if found.kind == KIND_REPLICATION_JOB)
    assert job.signals["source"] == SECONDARY
    assert job.signals["target"] == PRIMARY
    assert job.parent_native_id.endswith(SECONDARY)


# --- T-033: health mapping ----------------------------------------------------


def test_the_declared_mapping_turns_proxmox_words_into_the_closed_set() -> None:
    assert PROXMOX_STATUS_MAPPING.state_for("running") is ResourceHealth.HEALTHY
    assert PROXMOX_STATUS_MAPPING.state_for("offline") is ResourceHealth.UNHEALTHY
    assert PROXMOX_STATUS_MAPPING.state_for("available") is ResourceHealth.HEALTHY


def test_a_state_nobody_mapped_becomes_unknown_rather_than_healthy() -> None:
    assert PROXMOX_STATUS_MAPPING.state_for("reticulating") is ResourceHealth.UNKNOWN


def test_a_template_is_maintenance_rather_than_a_stopped_guest() -> None:
    """A template is not running by design, and counting it as a fault is noise."""
    assert PROXMOX_STATUS_MAPPING.state_for("template") is ResourceHealth.MAINTENANCE


async def test_the_raw_provider_status_is_retained_beside_the_verdict() -> None:
    page, _ = await sweep()

    guest = next(found for found in page.resources if found.kind == KIND_CONTAINER)

    assert guest.provider_status == "running"


# --- T-034: one node down -----------------------------------------------------


async def test_with_one_node_down_the_cluster_and_the_survivor_still_enumerate() -> None:
    page, _ = await sweep(ClusterState.NODE_DOWN)

    nodes = {found.display_name: found for found in page.resources if found.kind == KIND_NODE}

    assert set(nodes) == {PRIMARY, SECONDARY}
    assert nodes[PRIMARY].provider_status == "online"
    assert nodes[SECONDARY].provider_status == "offline"


async def test_the_down_nodes_guests_are_stale_rather_than_absent() -> None:
    page, _ = await sweep(ClusterState.NODE_DOWN)

    guests = [
        found for found in page.resources if found.kind in {KIND_CONTAINER, KIND_VIRTUAL_MACHINE}
    ]

    on_down_node = [found for found in guests if found.signals.get("node") == SECONDARY]
    assert on_down_node, "the guests on the down node vanished from the sweep"
    assert all(found.provider_status == "unknown" for found in on_down_node)
    assert all(
        found.signals["stale"] == "the node hosting it is not answering" for found in on_down_node
    )


async def test_a_sweep_with_a_node_down_is_still_complete() -> None:
    """It saw the whole inventory; part of the inventory is not answering."""
    page, _ = await sweep(ClusterState.NODE_DOWN)

    assert page.complete


# --- Bounds -------------------------------------------------------------------


async def test_a_sweep_that_runs_out_of_calls_suspends_at_a_cursor() -> None:
    source, _ = source_for()

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget(max_provider_calls=4))

    assert not page.complete
    assert page.cursor
    assert page.provider_calls <= 5


async def test_a_suspended_sweep_resumes_where_it_stopped() -> None:
    source, _ = source_for()
    first = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget(max_provider_calls=4))

    second = await source.discover(
        mode=DiscoveryMode.FULL, cursor=first.cursor, budget=SweepBudget()
    )

    assert second.complete
    assert second.resources


async def test_the_declared_call_budget_covers_the_reference_cluster() -> None:
    """NFR-001, declared rather than discovered after the fact."""
    source, transport = source_for()

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())

    assert page.provider_calls == len(transport.calls)
    assert page.provider_calls <= source.declaration.max_provider_calls


# --- T-038 / SC-011: masking --------------------------------------------------


def test_a_cloud_init_password_is_masked_before_it_can_be_stored() -> None:
    masked = masked_configuration(
        {"cipassword": "hunter2-the-operators-actual-password", "cores": 4}
    )

    assert "hunter2-the-operators-actual-password" not in json.dumps(masked)
    assert masked["cores"] == 4


def test_a_private_key_in_a_guest_configuration_is_masked() -> None:
    masked = masked_configuration(
        {"ssh-public-keys": "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1r\n"}
    )

    assert "b3BlbnNzaC1r" not in json.dumps(masked)


async def test_no_secret_from_a_guest_configuration_reaches_a_discovered_resource() -> None:
    """SC-011, end to end: the sweep is what would write it to the estate."""
    page, _ = await sweep()

    rendered = json.dumps(
        [
            {"attributes": dict(found.attributes), "signals": dict(found.signals)}
            for found in page.resources
        ]
    )

    assert "hunter2-the-operators-actual-password" not in rendered
    assert "another-secret-nobody-should-store" not in rendered
    assert "b3BlbnNzaC1rZXktdjEAAAAA" not in rendered


# --- FR-013c/d/e: the readings the API does not have -------------------------


def test_the_readings_the_api_cannot_give_are_unavailable_and_name_their_publisher() -> None:
    readings = supplementary_readings(node=SECONDARY, published=None)

    for name in ("failed_units", "bridges", "thin_pool_metadata"):
        reading = getattr(readings, name)
        assert not reading.available
        assert SUPPLEMENTARY_PUBLISHER in reading.published_by


def test_an_absent_supplementary_reading_is_never_reported_as_healthy() -> None:
    readings = supplementary_readings(node=SECONDARY, published=None)

    assert readings.health_verdict() is ResourceHealth.UNKNOWN
    assert "nothing is looking" in readings.summary()


def test_a_publisher_that_is_there_supplies_the_readings() -> None:
    readings = supplementary_readings(
        node=SECONDARY,
        published={
            "failed_units": ("corosync-qdevice.service", "mnt-TeraChad.mount"),
            "bridges": {"vmbr0": True},
            "thin_pool_metadata": {"pve/data": 3.35},
        },
    )

    assert readings.failed_units.require() == (
        "corosync-qdevice.service",
        "mnt-TeraChad.mount",
    )
    assert readings.health_verdict() is ResourceHealth.DEGRADED


def test_nothing_in_this_package_can_reach_a_shell_on_a_node() -> None:
    """FR-013d. The largest authority this system could hold, refused structurally."""
    banned = ("subprocess", "paramiko", "asyncssh", "os.system", "/nodes/{node}/execute")
    offenders = [
        f"{path.name}: {word}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for word in banned
        if word in path.read_text(encoding="utf-8")
    ]

    assert not offenders, "\n".join(offenders)


# --- FR-031 / FR-032: the operator's own inventory ---------------------------


INVENTORY = {
    "nodes": [
        {"name": PRIMARY, "role": "primary", "expected_state": "online"},
        {"name": SECONDARY, "role": "secondary", "expected_state": "online"},
    ],
    "guests": [
        {"vmid": 100, "kind": "lxc", "name": "plex", "expected_state": "running", "owner": "media"},
        {
            "vmid": 9000,
            "kind": "qemu",
            "name": "windows-lab",
            "expected_state": "running",
            "owner": "lab",
        },
    ],
}


def test_an_inventory_that_is_not_one_is_refused_with_what_is_wrong() -> None:
    with pytest.raises(InventoryInvalid, match="vmid"):
        Inventory.from_mapping({"guests": [{"kind": "lxc", "name": "plex"}]}, cluster="HAL9000")


def test_the_inventory_declares_intent_the_api_cannot_report() -> None:
    inventory = Inventory.from_mapping(INVENTORY, cluster="HAL9000")

    assert inventory.node("pve01").role == "primary"
    assert inventory.guest(100).owner == "media"


async def test_the_inventory_is_a_second_source_for_the_same_resources() -> None:
    """FR-031. Same identities, so feature 038's rule reconciles them to one record."""
    live, _ = await sweep()
    source = InventorySource(Inventory.from_mapping(INVENTORY, cluster="HAL9000"))

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())

    declared = {found.native_id for found in page.resources}
    observed = {found.native_id for found in live.resources}
    assert declared & observed, "the two sources describe different things entirely"


async def test_a_guest_the_inventory_expects_running_and_the_api_says_is_stopped_diverges() -> None:
    """FR-032. Both values retained, and the disagreement is expressible as a signal."""
    live, _ = await sweep()
    inventory = Inventory.from_mapping(INVENTORY, cluster="HAL9000")

    found = divergences(inventory, live.resources)

    assert any(
        divergence.field == "state"
        and divergence.expected == "running"
        and divergence.observed == "stopped"
        for divergence in found
    )


def test_a_divergence_renders_as_a_signal_rather_than_as_prose() -> None:
    inventory = Inventory.from_mapping(INVENTORY, cluster="HAL9000")

    found = divergences(inventory, ())

    assert all(divergence.as_signal()[0].startswith("divergence.") for divergence in found)


def test_the_integration_writes_to_nothing_a_control_plane_owns() -> None:
    """FR-033. A second writer is how drift becomes an outage."""
    import inspect

    source = inspect.getsource(ProxmoxDiscovery)

    for verb in (".post(", ".put(", ".delete("):
        assert verb not in source


# --- T-036 / T-037: verification ---------------------------------------------


async def test_verification_reports_the_cluster_its_node_count_and_its_version() -> None:
    transport = RecordedTransport(cluster=recorded(ClusterState.HEALTHY))
    client = ProxmoxClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    report = await ProxmoxVerifier().describe(client)

    assert report.cluster == "HAL9000"
    assert report.node_count == 2
    assert report.version == "9.2.6"


async def test_read_and_write_sufficiency_are_reported_separately() -> None:
    """SC-001. A read-only token is a supported and clearly-labelled choice."""
    transport = RecordedTransport(cluster=recorded(ClusterState.HEALTHY))
    client = ProxmoxClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    report = await ProxmoxVerifier().describe(client)

    assert report.privileges.read_sufficient
    assert not report.privileges.write_sufficient
    assert "read-only" in report.summary()


def test_an_insufficient_privilege_is_named_with_the_path_it_was_needed_for() -> None:
    """SC-002. Not a generic authorisation failure."""
    report = privilege_report({"/": {"Sys.Audit": 1}})

    assert not report.read_sufficient
    missing = {(gap.privilege, gap.path) for gap in report.missing_read}
    assert ("VM.Audit", "/vms") in missing
    assert "VM.Audit on /vms" in report.explain()


def test_every_read_privilege_says_what_stops_working_without_it() -> None:
    for privilege in READ_PRIVILEGES:
        assert privilege.grants.strip()
        assert privilege.path.startswith("/")


def test_the_write_privileges_are_declared_but_not_required_for_this_feature() -> None:
    report = privilege_report(
        {
            "/": {"Sys.Audit": 1, "Datastore.Audit": 1, "Sys.Syslog": 1},
            "/vms": {"VM.Audit": 1},
        }
    )

    assert report.read_sufficient
    assert {gap.privilege for gap in report.missing_write} == {
        privilege.privilege for privilege in WRITE_PRIVILEGES
    }


# --- T-040: the whole client, with no live cluster ---------------------------


@pytest.mark.parametrize("state", list(ClusterState))
async def test_every_recorded_state_sweeps_without_a_live_cluster(state: ClusterState) -> None:
    page, _ = await sweep(state)

    assert page.resources
    assert page.provider_calls > 0
