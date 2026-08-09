"""Proxmox, end to end: capability, client, proxy, API token, hypervisor.

Three scenarios, and each carries one thing through four layers that any of them
could quietly drop.

The first is the quorum margin. A cluster that is quorate, green, and has a margin
of zero is the reference cluster's actual standing state, and the arithmetic —
total votes minus the votes quorum requires — is the whole finding. A layer that
reported "quorate: true" and stopped would report the most important fact about a
two-node cluster as fine.

The second is the gap between a datastore's fill and a guest's own volume. The
datastore says 84%; the container inside it is at 99.6% of its own thin volume.
Those two numbers travel through different endpoints and different parsers, and
the one that matters is the one no datastore-level threshold would ever see.

The third is a backup job that exists and is switched off. Every count of "guests
with a backup job" includes them; the count that matters excludes them.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

CREDENTIAL: Final[dict[str, str]] = {
    "api_token": "ninjasre@pve!ninjasre=1a2b3c4d-5e6f-7890-abcd-ef1234567890",
    "username": "ninjasre@pve",
}


def _envelope(payload: object) -> object:
    """Return ``payload`` wrapped the way every Proxmox endpoint answers."""
    return {"data": payload}


CLUSTER_HEALTH: Final = IntegrationScenario(
    key="proxmox-cluster-health",
    integration="proxmox",
    capability="proxmox_cluster_health",
    arguments={},
    responses=(
        json_response(
            _envelope(
                [
                    {
                        "type": "cluster",
                        "id": "cluster",
                        "name": "HAL9000",
                        "version": 2,
                        "nodes": 2,
                        "quorate": 1,
                    },
                    {
                        "type": "node",
                        "id": "node/pve01",
                        "name": "pve01",
                        "online": 1,
                        "nodeid": 1,
                        "ip": "192.168.68.149",
                    },
                    {
                        "type": "node",
                        "id": "node/pve02",
                        "name": "pve02",
                        "online": 1,
                        "nodeid": 2,
                        "ip": "192.168.68.159",
                        "local": 1,
                    },
                    {
                        "type": "quorum",
                        "id": "quorum",
                        "quorate": 1,
                        "expected_votes": 2,
                        "total_votes": 2,
                        "quorum": 2,
                        "qdevice": "NA,NV,NMW",
                    },
                ]
            )
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="quorate with a margin of 0",
)

STORAGE_PRESSURE: Final = IntegrationScenario(
    key="proxmox-storage-pressure",
    integration="proxmox",
    capability="proxmox_storage_pressure",
    arguments={"node": "pve02"},
    responses=(
        json_response(
            _envelope(
                [
                    {
                        "storage": "local-lvm",
                        "type": "lvmthin",
                        "active": 1,
                        "shared": 0,
                        "total": 375_700_000_000,
                        "used": 317_300_000_000,
                        "content": "images,rootdir",
                    },
                    {
                        "storage": "externo-nfs-pve01",
                        "type": "nfs",
                        "active": 0,
                        "status": "unknown",
                        "shared": 1,
                    },
                ]
            )
        ),
        json_response(
            _envelope(
                [
                    {
                        "lv": "data",
                        "vg": "pve",
                        "lv_size": 375_700_000_000,
                        "data_percent": 84.46,
                        "metadata_percent": 3.35,
                        "lv_state": "available",
                    }
                ]
            )
        ),
        json_response(
            _envelope(
                [
                    {
                        "lv": "vm-100-disk-0",
                        "vg": "pve",
                        "lv_size": 107_374_182_400,
                        "data_percent": 99.60,
                    }
                ]
            )
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="vm-100-disk-0",
)

PROTECTION_GAPS: Final = IntegrationScenario(
    key="proxmox-protection-gaps",
    integration="proxmox",
    capability="proxmox_protection_gaps",
    arguments={},
    responses=(
        json_response(
            _envelope(
                [
                    {
                        "id": "backup-7d831311",
                        "comment": "pve01 baseline",
                        "enabled": 0,
                        "all": 1,
                        "schedule": "08:00",
                        "storage": "remote-backup",
                    },
                    {
                        "id": "backup-33b5e58a",
                        "comment": "pve02 baseline",
                        "enabled": 1,
                        "vmid": "100",
                        "schedule": "07:00",
                        "storage": "remote-backup",
                    },
                ]
            )
        ),
        json_response(
            _envelope(
                [
                    {"id": "node/pve01", "type": "node", "node": "pve01", "status": "online"},
                    {
                        "id": "lxc/100",
                        "type": "lxc",
                        "vmid": 100,
                        "name": "plex",
                        "node": "pve01",
                        "status": "running",
                    },
                    {
                        "id": "lxc/137",
                        "type": "lxc",
                        "vmid": 137,
                        "name": "prometheus",
                        "node": "pve01",
                        "status": "running",
                    },
                ]
            )
        ),
        json_response(_envelope([])),
    ),
    credential=CREDENTIAL,
    expected_summary="covered by no enabled backup job",
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (
    CLUSTER_HEALTH,
    STORAGE_PRESSURE,
    PROTECTION_GAPS,
)

__all__ = [
    "CLUSTER_HEALTH",
    "CREDENTIAL",
    "PROTECTION_GAPS",
    "SCENARIOS",
    "STORAGE_PRESSURE",
]
