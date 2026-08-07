"""The reads no API answers, against the output a real node actually produced.

Every sample below has the shape a node printed. The names in them are
pseudonyms — that is the whole point of the pipeline these feed — but the
columns, the spacing, the JSON keys and the awkward cases are as they came off
the wire, because a parser proved against tidied output is a parser proved
against nothing.
"""

from __future__ import annotations

import json

import pytest

from tools.mockplane.capture.parsers import (
    parse_boots,
    parse_bridges,
    parse_corosync,
    parse_failed_units,
    parse_findmnt,
    parse_lvs,
    parse_upgradable,
    parse_zfs_pools,
)

pytestmark = pytest.mark.unit


FAILED_UNITS = """\
  mnt-archive.mount                loaded failed failed Archive share
  mnt-vault.mount                  loaded failed failed Vault share
  corosync-qdevice.service         loaded failed failed Corosync Qdevice daemon
  gateway-hardening.service        loaded failed failed Gateway hardening
  metrics-agent.service            loaded failed failed Metrics agent
"""

LVS = json.dumps(
    {
        "report": [
            {
                "lv": [
                    {
                        "lv_name": "data",
                        "vg_name": "vg-system",
                        "lv_size": "375722000000B",
                        "data_percent": "84.46",
                        "metadata_percent": "3.35",
                        "pool_lv": "",
                    },
                    {
                        "lv_name": "data-pool",
                        "vg_name": "vg-bulk",
                        "lv_size": "999750000000B",
                        "data_percent": "72.38",
                        "metadata_percent": "31.98",
                        "pool_lv": "",
                    },
                    {
                        "lv_name": "vm-100-disk-0",
                        "vg_name": "vg-bulk",
                        "lv_size": "64000000000B",
                        "data_percent": "99.60",
                        "metadata_percent": "",
                        "pool_lv": "data-pool",
                    },
                ]
            }
        ]
    }
)

COROSYNC = """\
totem {
    version: 2
    cluster_name: cluster-example
    transport: knet
    crypto_cipher: aes256
}

nodelist {
    node {
        name: node01
        nodeid: 1
        quorum_votes: 1
    }
    node {
        name: node02
        nodeid: 2
        quorum_votes: 1
    }
}

quorum {
    provider: corosync_votequorum
}

totem_config {
    config_version: 2
}
"""

PVECM_STATUS = """\
Quorum information
------------------
Date:             Fri Aug  7 09:41:02 2026
Quorate:          Yes

Votequorum information
----------------------
Expected votes:   2
Highest expected: 2
Total votes:      2
Quorum:           2
Flags:            Quorate Qdevice

Membership information
----------------------
    Nodeid      Votes    Qdevice Name
         1          1   NA,NV,NMW node01
         2          1   NR        node02 (local)
         0          0            Qdevice
"""

FINDMNT = json.dumps(
    {
        "filesystems": [
            {
                "target": "/",
                "source": "/dev/mapper/vg--system-root",
                "fstype": "ext4",
                "children": [
                    {"target": "/mnt/archive", "source": "", "fstype": None},
                    {"target": "/mnt/bulk", "source": "//store/bulk", "fstype": "cifs"},
                ],
            }
        ]
    }
)

BOOTS = """\
 -2 4f0e1a2b3c4d5e6f7a8b Tue 2026-07-21 08:12:03 UTC—Tue 2026-07-21 19:40:11 UTC
 -1 9a8b7c6d5e4f3a2b1c0d Wed 2026-07-22 06:02:44 UTC—Sun 2026-08-02 11:19:57 UTC
  0 1122334455667788990a Sun 2026-08-02 11:21:10 UTC—Fri 2026-08-07 09:41:02 UTC
"""

UPGRADABLE = """\
Listing... Done
jq/stable-security 1.7.1-3 amd64 [upgradable from: 1.7.1-2]
libjq1/stable-security 1.7.1-3 amd64 [upgradable from: 1.7.1-2]
kernel-platform/stable 7.0.14-9 amd64 [upgradable from: 7.0.14-8]
"""

IP_LINK = json.dumps(
    [
        {"ifname": "lo", "linkinfo": None},
        {"ifname": "enp1s0", "linkinfo": {"info_kind": "device"}},
        {"ifname": "bridge0", "linkinfo": {"info_kind": "bridge"}},
    ]
)


def test_failed_units_are_read_as_names() -> None:
    assert parse_failed_units(FAILED_UNITS) == (
        "mnt-archive.mount",
        "mnt-vault.mount",
        "corosync-qdevice.service",
        "gateway-hardening.service",
        "metrics-agent.service",
    )


def test_no_failed_units_reads_as_none_rather_than_failing() -> None:
    assert parse_failed_units("") == ()


def test_pools_and_volumes_are_told_apart_by_what_they_carry() -> None:
    pools, volumes = parse_lvs(LVS)
    assert [pool.name for pool in pools] == ["data", "data-pool"]
    assert [volume.name for volume in volumes] == ["vm-100-disk-0"]


def test_the_metadata_percentage_survives_the_parse() -> None:
    pools, _ = parse_lvs(LVS)
    bulk = next(pool for pool in pools if pool.name == "data-pool")
    assert bulk.metadata_percent == 31.98
    assert bulk.data_percent == 72.38, "the number everybody watches must survive too"


def test_a_guests_own_volume_fill_is_a_separate_reading_from_its_pool() -> None:
    pools, volumes = parse_lvs(LVS)
    assert volumes[0].used_percent == 99.60
    assert next(pool for pool in pools if pool.name == "data-pool").data_percent == 72.38


def test_unreadable_lvs_output_yields_nothing_rather_than_raising() -> None:
    assert parse_lvs("not json at all") == ((), ())


def test_quorum_is_read_from_the_file_and_the_status_together() -> None:
    quorum = parse_corosync(COROSYNC, PVECM_STATUS)
    assert quorum.expected_votes == 2
    assert quorum.total_votes == 2
    assert quorum.quorum == 2
    assert quorum.quorate is True
    assert quorum.node_names == ("node01", "node02")


def test_a_quorum_device_in_the_membership_with_none_declared_is_visible() -> None:
    quorum = parse_corosync(COROSYNC, PVECM_STATUS)
    assert quorum.device_in_membership is True
    assert quorum.device_declared is False, "the configuration declares no device block"


def test_a_two_node_cluster_with_no_margin_says_so() -> None:
    quorum = parse_corosync(COROSYNC, PVECM_STATUS)
    assert quorum.margin == 0
    assert quorum.two_node is False
    assert quorum.wait_for_all is False


def test_a_commented_out_clause_does_not_count_as_declared() -> None:
    quorum = parse_corosync("quorum {\n # two_node: 1\n}", "")
    assert quorum.two_node is False


def test_a_mount_with_no_source_reads_as_unavailable() -> None:
    mounts = parse_findmnt(FINDMNT)
    by_target = {mount.target: mount for mount in mounts}
    assert by_target["/mnt/archive"].available is False
    assert by_target["/mnt/bulk"].available is True
    assert by_target["/"].available is True


def test_the_boot_history_puts_the_running_boot_at_zero() -> None:
    boots = parse_boots(BOOTS)
    assert [boot.ordinal for boot in boots] == [-2, -1, 0]


def test_the_security_subset_of_pending_packages_is_distinguishable() -> None:
    packages = parse_upgradable(UPGRADABLE)
    assert [package.name for package in packages] == ["jq", "libjq1", "kernel-platform"]
    assert [package.is_security for package in packages] == [True, True, False]
    assert packages[2].version == "7.0.14-9"


def test_only_bridges_are_reported_as_bridges() -> None:
    assert parse_bridges(IP_LINK) == ("bridge0",)


def test_no_zfs_reads_as_no_pools_rather_than_as_an_error() -> None:
    assert parse_zfs_pools("no pools available\n") == ()
    assert parse_zfs_pools("tank\t1.8T\t900G\t900G\t-\t12%\t50%\t1.00x\tONLINE\t-") == ("tank",)
