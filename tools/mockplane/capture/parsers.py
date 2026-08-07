"""Parsers for the reads no API answers, each returning a value rather than text.

These are the reason SSH is the transport. Failed units, LVM thin-pool
*metadata* percentage, the corosync configuration as written, mount state and
boot history are absent from the cluster's REST surface, and every one of them
is either a shipped detector or a finding in a real postmortem. A capture that
read only the API would produce fixtures for screens that never show the thing
that actually broke.

Each parser is total: unreadable input yields nothing rather than raising. A
capture that dies because one node phrased its unit list differently is a
capture nobody runs twice, and the missed-read report is where an empty result
becomes visible.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

_WHITESPACE: Final = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ThinPoolReading:
    """One LVM thin pool, with the metadata percentage no datastore view shows."""

    name: str
    volume_group: str
    size_bytes: int
    data_percent: float
    metadata_percent: float


@dataclass(frozen=True, slots=True)
class VolumeReading:
    """One thin volume's fill, which is a different question from its datastore's."""

    name: str
    volume_group: str
    pool: str
    size_bytes: int
    used_percent: float


@dataclass(frozen=True, slots=True)
class MountReading:
    """One mount, and whether it is actually there."""

    target: str
    source: str
    filesystem: str
    available: bool


@dataclass(frozen=True, slots=True)
class QuorumReading:
    """Quorum as the cluster stack reports it and as the file declares it.

    Both, because they disagree in the case that matters: a quorum device can
    appear in the membership view, contribute zero votes, and have a dead
    daemon, which reads as "configured" to anything that counts devices.
    """

    expected_votes: int = 0
    total_votes: int = 0
    quorum: int = 0
    quorate: bool = False
    config_version: int = 0
    two_node: bool = False
    wait_for_all: bool = False
    device_declared: bool = False
    device_in_membership: bool = False
    node_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def margin(self) -> int:
        """Return how many votes may be lost before the cluster stops being quorate."""
        return max(self.total_votes - self.quorum, 0)


@dataclass(frozen=True, slots=True)
class BootReading:
    """One entry of the boot history, which is how a never-booted kernel is caught."""

    ordinal: int
    started_at: str


@dataclass(frozen=True, slots=True)
class PackageReading:
    """One pending package, and whether it came from a security pocket."""

    name: str
    version: str
    is_security: bool


def parse_failed_units(text: str) -> tuple[str, ...]:
    """Return the unit names ``systemctl list-units --failed`` printed.

    The plain, no-legend form is one unit per line with the name first, so this
    reads the first field and ignores the rest — which keeps it working when a
    node's ``systemd`` pads the columns differently.
    """
    units: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("●") and len(stripped) == 1:
            continue
        # A bullet marks a failed unit on some versions and is absent on others.
        stripped = stripped.lstrip("●").strip()
        name = _WHITESPACE.split(stripped)[0]
        if name and "." in name:
            units.append(name)
    return tuple(units)


def parse_lvs(raw: str) -> tuple[tuple[ThinPoolReading, ...], tuple[VolumeReading, ...]]:
    """Return the thin pools and the thin volumes ``lvs --reportformat json`` printed.

    A pool has a metadata percentage and no pool of its own; a volume has a pool
    and a data percentage that is its own fill. Distinguishing them by which
    fields are populated rather than by a flag keeps this working against the
    two spellings ``lvs`` has used for the pool column.
    """
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return (), ()
    reports = document.get("report") if isinstance(document, dict) else None
    if not isinstance(reports, Sequence):
        return (), ()

    pools: list[ThinPoolReading] = []
    volumes: list[VolumeReading] = []
    for report in reports:
        rows = report.get("lv") if isinstance(report, Mapping) else None
        if not isinstance(rows, Sequence):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("lv_name", ""))
            group = str(row.get("vg_name", ""))
            pool = str(row.get("pool_lv", ""))
            size = _bytes(row.get("lv_size"))
            data = _percent(row.get("data_percent"))
            metadata = _percent(row.get("metadata_percent"))
            if not name:
                continue
            if pool:
                volumes.append(
                    VolumeReading(
                        name=name,
                        volume_group=group,
                        pool=pool,
                        size_bytes=size,
                        used_percent=data,
                    )
                )
            elif row.get("metadata_percent") not in (None, ""):
                pools.append(
                    ThinPoolReading(
                        name=name,
                        volume_group=group,
                        size_bytes=size,
                        data_percent=data,
                        metadata_percent=metadata,
                    )
                )
    return tuple(pools), tuple(volumes)


def parse_findmnt(raw: str) -> tuple[MountReading, ...]:
    """Return every mount ``findmnt --json`` printed, nested ones included.

    A network share that is down still appears; what distinguishes it is a
    source the node could not resolve, which is why availability is derived
    rather than assumed from presence.
    """
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    roots = document.get("filesystems") if isinstance(document, dict) else None
    if not isinstance(roots, Sequence):
        return ()
    return tuple(_mounts(roots))


def parse_corosync(text: str, status: str = "") -> QuorumReading:
    """Return what the corosync configuration declares, and what the stack reports.

    ``text`` is ``corosync.conf`` as written; ``status`` is ``pvecm status``.
    Read together on purpose: the file says whether a quorum device, a
    ``two_node`` clause or ``wait_for_all`` was ever configured, and the status
    says how many votes actually exist. A device in the membership view with no
    votes is only visible when both are in hand.
    """
    body = _strip_comments(text)
    node_names = tuple(re.findall(r"\bname:\s*(\S+)", body))
    config_version = _int(re.search(r"\bconfig_version:\s*(\d+)", body))
    two_node = bool(re.search(r"\btwo_node:\s*1\b", body))
    wait_for_all = bool(re.search(r"\bwait_for_all:\s*1\b", body))
    device_declared = bool(re.search(r"\bdevice\s*\{", body))

    expected = _int(re.search(r"Expected votes:\s*(\d+)", status))
    total = _int(re.search(r"Total votes:\s*(\d+)", status))
    quorum = _int(re.search(r"Quorum:\s*(\d+)", status))
    quorate = bool(re.search(r"Quorate:\s*Yes", status))
    device_seen = "Qdevice" in status

    return QuorumReading(
        expected_votes=expected,
        total_votes=total,
        quorum=quorum,
        quorate=quorate,
        config_version=config_version,
        two_node=two_node,
        wait_for_all=wait_for_all,
        device_declared=device_declared,
        device_in_membership=device_seen,
        node_names=node_names,
    )


def parse_boots(text: str) -> tuple[BootReading, ...]:
    """Return the boot history ``journalctl --list-boots`` printed.

    The ordinal is what matters: ``0`` is the running boot, and a kernel
    installed since the last entry is a kernel whose first real boot will be an
    unplanned one.
    """
    boots: list[BootReading] = []
    for line in text.splitlines():
        fields = _WHITESPACE.split(line.strip())
        if len(fields) < 3:
            continue
        try:
            ordinal = int(fields[0])
        except ValueError:
            continue
        boots.append(BootReading(ordinal=ordinal, started_at=" ".join(fields[2:4])))
    return tuple(boots)


def parse_upgradable(text: str) -> tuple[PackageReading, ...]:
    """Return the pending packages ``apt list --upgradable`` printed."""
    packages: list[PackageReading] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Listing") or "/" not in stripped:
            continue
        name, _, rest = stripped.partition("/")
        pocket, _, remainder = rest.partition(" ")
        version = _WHITESPACE.split(remainder.strip())[0] if remainder.strip() else ""
        packages.append(
            PackageReading(
                name=name.strip(),
                version=version,
                is_security="security" in pocket.lower(),
            )
        )
    return tuple(packages)


def parse_bridges(raw: str) -> tuple[str, ...]:
    """Return the bridge interfaces ``ip -json link show`` printed.

    Everything in the reference environment depends on one bridge and nothing
    watches it; an upgrade that renamed the interfaces underneath it took both
    nodes off the network and needed physical access to recover.
    """
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(document, Sequence):
        return ()
    found: list[str] = []
    for entry in document:
        if not isinstance(entry, Mapping):
            continue
        info = entry.get("linkinfo")
        kind = info.get("info_kind") if isinstance(info, Mapping) else None
        if kind == "bridge":
            found.append(str(entry.get("ifname", "")))
    return tuple(name for name in found if name)


def parse_zfs_pools(text: str) -> tuple[str, ...]:
    """Return the ZFS pools ``zpool list -H`` printed, which is routinely none.

    Worth reading precisely because the answer is often empty: a specification
    that leads with ZFS is aimed at the wrong technology for a cluster that has
    none, and "no pools available" is the fact that settles it.
    """
    pools: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "no pools available" in stripped.lower():
            continue
        pools.append(_WHITESPACE.split(stripped)[0])
    return tuple(pools)


def _mounts(entries: Sequence[Any]) -> Iterator[MountReading]:
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        source = str(entry.get("source", ""))
        yield MountReading(
            target=str(entry.get("target", "")),
            source=source,
            filesystem=str(entry.get("fstype", "")),
            available=bool(source) and entry.get("fstype") not in (None, ""),
        )
        children = entry.get("children")
        if isinstance(children, Sequence):
            yield from _mounts(children)


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _int(found: re.Match[str] | None) -> int:
    return int(found.group(1)) if found else 0


def _percent(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _bytes(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "").strip().rstrip("Bb")
    try:
        return int(float(text))
    except ValueError:
        return 0


__all__ = [
    "BootReading",
    "MountReading",
    "PackageReading",
    "QuorumReading",
    "ThinPoolReading",
    "VolumeReading",
    "parse_boots",
    "parse_bridges",
    "parse_corosync",
    "parse_failed_units",
    "parse_findmnt",
    "parse_lvs",
    "parse_upgradable",
    "parse_zfs_pools",
]
