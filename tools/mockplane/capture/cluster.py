"""Reading a cluster through the read-only channel, both halves, into one value.

``pvesh`` answers everything the cluster's own API covers, and its payloads are
byte-identical to what a REST client will return — which is what makes this half
reusable when the real integration lands, and deletable at the same moment. The
shell answers what no API level reports. Each read is attributed, each failure
is reported rather than swallowed, and the result is one :class:`ClusterReading`
the projection turns into fixtures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tools.mockplane.allowlist import CommandRefused
from tools.mockplane.capture.channel import ChannelError, ReadOnlyChannel
from tools.mockplane.capture.gateway import MissedEndpoint
from tools.mockplane.capture.parsers import (
    QuorumReading,
    parse_boots,
    parse_bridges,
    parse_corosync,
    parse_failed_units,
    parse_findmnt,
    parse_lvs,
    parse_upgradable,
    parse_zfs_pools,
)
from tools.mockplane.capture.projection import (
    BackupJobReading,
    ClusterReading,
    DatastoreReading,
    GuestReading,
    NodeReading,
)
from tools.mockplane.records import Provenance


@dataclass(slots=True)
class _Reader:
    """One read at a time, collecting what could not be made rather than raising."""

    channel: ReadOnlyChannel
    missed: list[MissedEndpoint] = field(default_factory=list)

    def text(self, node: str, command: str, about: str) -> str:
        try:
            return self.channel.read(node, command)
        except (ChannelError, CommandRefused) as failure:
            self.missed.append(
                MissedEndpoint(about, "READ", command, Provenance.SHELL.value, str(failure))
            )
            return ""

    def json(self, node: str, command: str, about: str) -> Any:
        try:
            return self.channel.read_json(node, command)
        except (ChannelError, CommandRefused) as failure:
            self.missed.append(
                MissedEndpoint(about, "READ", command, Provenance.PVESH.value, str(failure))
            )
            return None


def read_cluster(
    channel: ReadOnlyChannel,
    nodes: Sequence[str],
    *,
    captured_at: str,
    roles: Mapping[str, str] | None = None,
) -> tuple[ClusterReading, tuple[MissedEndpoint, ...]]:
    """Return one reading of the cluster, and the reads that could not be made."""
    reader = _Reader(channel=channel)
    if not nodes:
        return _empty(captured_at), ()

    first = nodes[0]
    cluster_status = reader.json(first, "pvesh get /cluster/status --output-format json", "quorum")
    quorum_text = reader.text(first, "pvecm status", "quorum")
    corosync = reader.text(first, "cat /etc/pve/corosync.conf", "quorum")
    quorum = parse_corosync(corosync, quorum_text)
    if quorum.expected_votes == 0 and isinstance(cluster_status, Sequence):
        quorum = _quorum_from_status(quorum, cluster_status)

    backups = reader.json(first, "pvesh get /cluster/backup --output-format json", "backups")
    replication = reader.json(
        first, "pvesh get /cluster/replication --output-format json", "replication"
    )

    node_readings: list[NodeReading] = []
    guests: list[GuestReading] = []
    datastores: list[DatastoreReading] = []

    for name in nodes:
        status = reader.json(name, f"pvesh get /nodes/{name}/status --output-format json", "node")
        packages = reader.text(name, "apt list --upgradable", "packages")
        pending = parse_upgradable(packages)
        lvs_output = reader.text(
            name,
            "lvs --reportformat json --units b --options "
            "lv_name,vg_name,lv_size,data_percent,metadata_percent,pool_lv",
            "storage",
        )
        pools, volumes = parse_lvs(lvs_output)

        node_readings.append(
            NodeReading(
                name=name,
                role=(roles or {}).get(name, "secondary"),
                version=str(_get(status, "pveversion") or ""),
                kernel_running=reader.text(name, "uname -r", "kernel").strip(),
                kernel_installed=_installed_kernel(pending),
                cpu_percent=_percent_of(_get(status, "cpu")),
                memory_percent=_ratio(_get(status, "memory")),
                root_filesystem_percent=_ratio(_get(status, "rootfs")),
                failed_units=parse_failed_units(
                    reader.text(
                        name,
                        "systemctl list-units --failed --no-legend --plain --no-pager",
                        "units",
                    )
                ),
                thin_pools=pools,
                volumes=volumes,
                mounts=parse_findmnt(reader.text(name, "findmnt --json", "mounts")),
                boots=parse_boots(reader.text(name, "journalctl --list-boots --no-pager", "boots")),
                packages=pending,
                bridges=parse_bridges(reader.text(name, "ip -json link show", "bridges")),
                zfs_pools=parse_zfs_pools(reader.text(name, "zpool list -H", "zfs")),
            )
        )

        for kind, endpoint in (("container", "lxc"), ("virtual-machine", "qemu")):
            found = reader.json(
                name, f"pvesh get /nodes/{name}/{endpoint} --output-format json", "guests"
            )
            for entry in found if isinstance(found, Sequence) else ():
                if not isinstance(entry, Mapping):
                    continue
                guests.append(
                    GuestReading(
                        vmid=str(entry.get("vmid", "")),
                        name=str(entry.get("name", "")),
                        kind=kind,
                        node=name,
                        state=str(entry.get("status", "unknown")),
                        cpu_percent=_percent_of(entry.get("cpu")),
                        memory_percent=_of(entry, "mem", "maxmem"),
                        tags=tuple(sorted(str(entry.get("tags", "")).split(";")))
                        if entry.get("tags")
                        else (),
                    )
                )

        stores = reader.json(
            name, f"pvesh get /nodes/{name}/storage --output-format json", "datastores"
        )
        for entry in stores if isinstance(stores, Sequence) else ():
            if not isinstance(entry, Mapping):
                continue
            active = entry.get("active")
            datastores.append(
                DatastoreReading(
                    name=str(entry.get("storage", "")),
                    node=name,
                    kind=str(entry.get("type", "")),
                    used_bytes=_optional_int(entry.get("used")),
                    total_bytes=_optional_int(entry.get("total")),
                    status="available" if active else "unknown",
                )
            )

    return (
        ClusterReading(
            captured_at=captured_at,
            nodes=tuple(node_readings),
            guests=tuple(guests),
            datastores=tuple(datastores),
            backup_jobs=tuple(_backup_jobs(backups)),
            quorum=quorum,
            replication_jobs=tuple(
                entry for entry in (replication or ()) if isinstance(entry, Mapping)
            ),
        ),
        tuple(reader.missed),
    )


def _empty(captured_at: str) -> ClusterReading:
    return ClusterReading(
        captured_at=captured_at,
        nodes=(),
        guests=(),
        datastores=(),
        backup_jobs=(),
        quorum=QuorumReading(),
    )


def _quorum_from_status(quorum: QuorumReading, status: Sequence[Any]) -> QuorumReading:
    """Return ``quorum`` with the vote counts the cluster API reported filled in."""
    votes = 0
    expected = 0
    for entry in status:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("type") == "cluster":
            expected = int(entry.get("nodes", 0) or 0)
            quorate = bool(entry.get("quorate"))
            quorum = QuorumReading(
                expected_votes=expected,
                total_votes=quorum.total_votes,
                quorum=quorum.quorum,
                quorate=quorate,
                config_version=quorum.config_version,
                two_node=quorum.two_node,
                wait_for_all=quorum.wait_for_all,
                device_declared=quorum.device_declared,
                device_in_membership=quorum.device_in_membership,
                node_names=quorum.node_names,
            )
        elif entry.get("type") == "node":
            votes += int(entry.get("online", 0) or 0)
    return QuorumReading(
        expected_votes=quorum.expected_votes or expected,
        total_votes=quorum.total_votes or votes,
        quorum=quorum.quorum or expected,
        quorate=quorum.quorate,
        config_version=quorum.config_version,
        two_node=quorum.two_node,
        wait_for_all=quorum.wait_for_all,
        device_declared=quorum.device_declared,
        device_in_membership=quorum.device_in_membership,
        node_names=quorum.node_names,
    )


def _backup_jobs(document: Any) -> list[BackupJobReading]:
    if not isinstance(document, Sequence):
        return []
    jobs: list[BackupJobReading] = []
    for entry in document:
        if not isinstance(entry, Mapping):
            continue
        vmids = str(entry.get("vmid", ""))
        jobs.append(
            BackupJobReading(
                job_id=str(entry.get("id", "")),
                comment=str(entry.get("comment", "")),
                node=str(entry.get("node")) if entry.get("node") else None,
                schedule=str(entry.get("schedule", "")),
                enabled=str(entry.get("enabled", "0")) not in {"0", "false", "False"},
                covers_all=str(entry.get("all", "0")) in {"1", "true", "True"},
                vmids=tuple(part for part in vmids.split(",") if part),
                keep_last=int(entry.get("keep-last", 0) or 0),
            )
        )
    return jobs


def _installed_kernel(packages: Sequence[Any]) -> str:
    for package in packages:
        name = getattr(package, "name", "")
        if "kernel" in name and "-pve" not in name:
            return str(getattr(package, "version", ""))
    return ""


def _get(document: Any, key: str) -> Any:
    return document.get(key) if isinstance(document, Mapping) else None


def _percent_of(value: Any) -> float:
    try:
        return round(float(value) * 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _ratio(document: Any) -> float:
    if not isinstance(document, Mapping):
        return 0.0
    used: Any = document.get("used")
    total: Any = document.get("total")
    try:
        return round(float(used) * 100.0 / float(total), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _of(entry: Mapping[str, Any], used_key: str, total_key: str) -> float:
    try:
        return round(float(entry[used_key]) * 100.0 / float(entry[total_key]), 2)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["read_cluster"]
