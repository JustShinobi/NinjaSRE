"""The promises that are about every Proxmox investigation tool rather than one.

Each of these is checked by sweeping the whole set rather than by a row per
tool, because the failure mode is a tool added later that quietly does not keep
the promise — and a per-tool test is the thing nobody writes for the new one.

``every tool is read-only``
    Declared, and asserted structurally rather than by reading the code: the
    declaration is what the approval gate consults, so a tool that reads and
    declares otherwise is as dangerous as one that writes.

``every tool survives an unreachable cluster``
    And says what it could not determine. An investigation told "no results"
    concludes something about the estate; one told "nothing answered" concludes
    something about the deployment, and only the second is true.

``every tool answers on its own``
    No tool may depend on another having been called first. The loop selects a
    subset, and a tool that only works second is a tool that fails whenever it
    is chosen first.

``every result is bounded``
    A cluster with a thousand snapshots must not produce a thousand-entry
    payload, and a bounded list must say that it was bounded and by what — a
    reader who has to infer from a list of exactly twenty whether there were
    twenty-one will sometimes infer wrong.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from capabilities.registry.discovery import discover
from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from integrations.proxmox.investigation import MAX_REPORTED_ITEMS
from integrations.proxmox.schema import INTEGRATION
from integrations.proxmox.tools.backup_coverage import proxmox_backup_coverage
from integrations.proxmox.tools.backup_failures import proxmox_backup_failures
from integrations.proxmox.tools.clock_skew import proxmox_clock_skew
from integrations.proxmox.tools.cluster_health import proxmox_cluster_health
from integrations.proxmox.tools.corosync_links import proxmox_corosync_links
from integrations.proxmox.tools.datastore_availability import proxmox_datastore_availability
from integrations.proxmox.tools.disk_health import proxmox_disk_health
from integrations.proxmox.tools.guest_pressure import proxmox_guest_pressure
from integrations.proxmox.tools.guest_start_diagnosis import proxmox_guest_start_diagnosis
from integrations.proxmox.tools.guest_tasks import proxmox_guest_tasks
from integrations.proxmox.tools.ha_state import proxmox_ha_state
from integrations.proxmox.tools.migration_feasibility import proxmox_migration_feasibility
from integrations.proxmox.tools.orphaned_volumes import proxmox_orphaned_volumes
from integrations.proxmox.tools.protection_gaps import proxmox_protection_gaps
from integrations.proxmox.tools.quorum_status import proxmox_quorum_status
from integrations.proxmox.tools.reclaimable_space import proxmox_reclaimable_space
from integrations.proxmox.tools.replication_lag import proxmox_replication_lag
from integrations.proxmox.tools.storage_pressure import proxmox_storage_pressure
from integrations.proxmox.tools.zfs_health import proxmox_zfs_health
from tests.support.proxmox import (
    PRIMARY,
    SECONDARY,
    ZFS_POOL_DETAIL,
    ZFS_POOLS,
    ClusterState,
    investigating,
)

pytestmark = pytest.mark.contract

#: Every investigation capability, with arguments that name something the
#: recorded cluster actually has. A table rather than a fixture per tool,
#: because the point of every test below is that it covers all of them.
INVOCATIONS: tuple[tuple[str, Callable[[], Awaitable[CapabilityResult]]], ...] = (
    ("proxmox_cluster_health", lambda: proxmox_cluster_health()),
    ("proxmox_quorum_status", lambda: proxmox_quorum_status()),
    ("proxmox_corosync_links", lambda: proxmox_corosync_links()),
    ("proxmox_ha_state", lambda: proxmox_ha_state()),
    ("proxmox_clock_skew", lambda: proxmox_clock_skew()),
    ("proxmox_storage_pressure", lambda: proxmox_storage_pressure(SECONDARY)),
    ("proxmox_zfs_health", lambda: proxmox_zfs_health(SECONDARY)),
    ("proxmox_disk_health", lambda: proxmox_disk_health(SECONDARY)),
    ("proxmox_reclaimable_space", lambda: proxmox_reclaimable_space(SECONDARY)),
    ("proxmox_orphaned_volumes", lambda: proxmox_orphaned_volumes()),
    ("proxmox_datastore_availability", lambda: proxmox_datastore_availability()),
    (
        "proxmox_guest_start_diagnosis",
        lambda: proxmox_guest_start_diagnosis(SECONDARY, 100, kind="lxc"),
    ),
    ("proxmox_guest_pressure", lambda: proxmox_guest_pressure(SECONDARY, 100, kind="lxc")),
    ("proxmox_guest_tasks", lambda: proxmox_guest_tasks(SECONDARY, 100, kind="lxc")),
    (
        "proxmox_migration_feasibility",
        lambda: proxmox_migration_feasibility(SECONDARY, 100, kind="lxc"),
    ),
    ("proxmox_protection_gaps", lambda: proxmox_protection_gaps()),
    ("proxmox_backup_coverage", lambda: proxmox_backup_coverage()),
    ("proxmox_backup_failures", lambda: proxmox_backup_failures()),
    ("proxmox_replication_lag", lambda: proxmox_replication_lag()),
)

IDS = tuple(name for name, _ in INVOCATIONS)

#: Everything in the catalogue that reaches Proxmox at all, reads and writes.
REACHES_PROXMOX = tuple(
    found for found in discover().tools if found.metadata.evidence_source == INTEGRATION
)

#: The *investigation* capabilities, which is what this file is about. Selected
#: by where they live rather than by name: a tool under the vendor's own package
#: is a read by construction, and the remediation writes live in the
#: cross-vendor tree behind the approval gate.
DECLARED = tuple(
    found
    for found in REACHES_PROXMOX
    if found.source_module.startswith("integrations.proxmox.tools")
)


def test_the_sweep_below_covers_every_declared_proxmox_capability() -> None:
    """Otherwise every promise here is a promise about whatever was remembered."""
    declared = {found.name for found in DECLARED}

    assert declared == set(IDS), f"unswept: {sorted(declared - set(IDS))}"


def test_anything_else_reaching_proxmox_is_a_gated_write() -> None:
    """The other half, so "it is not an investigation tool" cannot mean "unexamined".

    A capability that reaches Proxmox and is not in the vendor's own package is
    a remediation write, and it declares four components, an approval, and a
    rollback plan or planner. There is no third category, and a tool that landed
    in one fails here.
    """
    from capabilities.tools.remediation import COMPONENTS

    gated = {bundle.capability for bundle in COMPONENTS}
    outside = [found for found in REACHES_PROXMOX if found not in DECLARED]

    assert outside, "the hypervisor writes have gone missing from the catalogue"
    for found in outside:
        assert found.name in gated, f"{found.name}: reaches Proxmox and is not a gated write"
        assert found.metadata.side_effect_level.needs_approval, found.name
        assert found.metadata.requires_approval, found.name
        assert found.metadata.rollback_plan or found.metadata.rollback_planner, found.name


# --- SC-012: read-only, structurally -----------------------------------------


def test_every_proxmox_capability_declares_itself_a_read() -> None:
    for found in DECLARED:
        assert found.metadata.side_effect_level is SideEffectLevel.READ, (
            f"{found.name}: declares {found.metadata.side_effect_level}"
        )
        assert not found.metadata.requires_approval
        assert found.metadata.parallel_safe, (
            f"{found.name}: a read that is not parallel-safe is a read with state"
        )


def test_no_proxmox_capability_module_calls_anything_that_writes() -> None:
    """The declaration is a claim; this is the check that the claim is true."""
    import inspect

    from integrations.proxmox import tools

    for name in tools.__all__:
        source = inspect.getsource(inspect.getmodule(getattr(tools, name)))
        for verb in (".post(", ".put(", ".delete(", ".patch("):
            assert verb not in source, f"{name}: calls {verb}"


# --- NFR-003: an unreachable cluster is reported, not imagined ---------------


@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_every_tool_against_an_unreachable_cluster_says_what_it_could_not_read(
    name: str, call: Callable[[], Awaitable[CapabilityResult]]
) -> None:
    with investigating(unreachable=True):
        result = await call()

    assert not result.succeeded, f"{name}: reported success against a cluster that never answered"
    assert result.error is not None
    assert result.error.classification is not CapabilityErrorClass.NOT_FOUND, (
        f"{name}: an unreachable cluster read as an absent thing"
    )
    assert result.error.message.strip(), f"{name}: failed with nothing a reader can act on"
    assert INTEGRATION in result.error.message.lower() or "endpoint" in result.error.message


@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_every_tool_with_no_integration_bound_says_so_by_name(
    name: str, call: Callable[[], Awaitable[CapabilityResult]]
) -> None:
    """ "Nothing was configured" and "the vendor had nothing to say" go different places."""
    result = await call()

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert INTEGRATION in result.error.message


# --- NFR-003: every answer carries its holes ---------------------------------


@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_every_successful_answer_carries_what_it_could_not_determine(
    name: str, call: Callable[[], Awaitable[CapabilityResult]]
) -> None:
    with investigating():
        result = await call()

    assert result.succeeded, f"{name}: {result.error}"
    assert isinstance(result.value, dict)
    assert "undetermined" in result.value, (
        f"{name}: returned an answer with no account of what it could not read"
    )
    for entry in result.value["undetermined"]:
        assert entry["question"].strip(), f"{name}: an unanswered question with no question"
        assert entry["reason"].strip(), f"{name}: an unanswered question with no reason"


# --- NFR-005: no tool depends on another having run --------------------------


@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_every_tool_answers_as_the_first_call_of_a_run(
    name: str, call: Callable[[], Awaitable[CapabilityResult]]
) -> None:
    """A tool that only works second fails whenever the loop chooses it first."""
    with investigating() as transport:
        result = await call()

    assert result.succeeded, f"{name}: {result.error}"
    assert transport.seen, f"{name}: answered without reading anything"
    assert result.evidence and result.evidence[0].summary.strip()


# --- NFR-002: bounded, by ranking, and it says so ----------------------------


@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_no_tool_returns_an_unbounded_list(
    name: str, call: Callable[[], Awaitable[CapabilityResult]]
) -> None:
    """Against a cluster with a thousand of everything a tool could list."""
    with investigating(responses=_a_thousand_of_everything()):
        result = await call()

    assert result.succeeded, f"{name}: {result.error}"
    _assert_bounded(name, result.value)


async def test_a_thousand_snapshots_are_ranked_before_they_are_cut() -> None:
    """Truncation would return twenty arbitrary snapshots; ranking returns the twenty."""
    with investigating(responses=_a_thousand_of_everything()):
        result = await proxmox_reclaimable_space(SECONDARY)

    bound = result.value["bounds"]["items"]
    assert bound["bounded"]
    assert bound["total"] >= 1_000
    assert bound["shown"] == MAX_REPORTED_ITEMS
    assert bound["ranked_by"].strip()
    sizes = [item["reclaims_bytes"] for item in result.value["items"]]
    assert sizes == sorted(sizes, reverse=True), "cut before it was ranked"


async def test_a_pool_that_a_node_does_have_is_still_read_boundedly() -> None:
    """The ZFS path has its own traversal, so it gets its own ceiling check."""
    with investigating(
        responses={
            f"/nodes/{SECONDARY}/disks/zfs": list(ZFS_POOLS),
            f"/nodes/{SECONDARY}/disks/zfs/tank": ZFS_POOL_DETAIL,
        }
    ):
        result = await proxmox_zfs_health(SECONDARY)

    assert result.value["applicable"]
    for pool in result.value["pools"]:
        assert len(pool["devices"]) <= MAX_REPORTED_ITEMS * 10


def _a_thousand_of_everything() -> dict[str, Any]:
    """Return a cluster with more of every listable thing than anything should read."""
    return {
        f"/nodes/{SECONDARY}/lxc/100/snapshot": [
            {"name": f"auto-{index:04d}", "snaptime": 1_700_000_000 + index}
            for index in range(1_000)
        ],
        f"/nodes/{SECONDARY}/storage/local-lvm/content": [
            {
                "volid": f"local-lvm:vm-{9_000 + index}-disk-0",
                "size": index * 1_000,
                "vmid": 9_000 + index,
            }
            for index in range(1_000)
        ],
        f"/nodes/{SECONDARY}/tasks": [
            {
                "upid": f"UPID:pve02:{index:08X}:0511D6A2:68943A10:vzdump:100:root@pam:",
                "type": "vzdump",
                "status": "job errors",
                "starttime": 1_754_800_000 + index,
                "endtime": 1_754_800_100 + index,
                "node": SECONDARY,
                "user": "root@pam",
            }
            for index in range(1_000)
        ],
        "/cluster/log": [
            {
                "id": index,
                "node": PRIMARY,
                "pri": 3,
                "tag": "corosync",
                "time": 1_754_802_000 + index,
                "msg": "link: host: 2 link: 0 is down"
                if index % 2
                else "link: host: 2 link: 0 is up",
            }
            for index in range(1_000)
        ],
    }


def _assert_bounded(name: str, value: Any, *, path: str = "") -> None:
    """Assert that no list anywhere in ``value`` is longer than the declared ceiling."""
    if isinstance(value, dict):
        for key, entry in value.items():
            _assert_bounded(name, entry, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        assert len(value) <= MAX_REPORTED_ITEMS, (
            f"{name}: {path or 'the result'} carries {len(value)} entries, over the "
            f"{MAX_REPORTED_ITEMS} ceiling"
        )
        for index, entry in enumerate(value):
            _assert_bounded(name, entry, path=f"{path}[{index}]")


# --- SC-010's other half: the states a tool has to survive -------------------


@pytest.mark.parametrize("state", tuple(ClusterState), ids=lambda state: state.value)
@pytest.mark.parametrize(("name", "call"), INVOCATIONS, ids=IDS)
async def test_every_tool_answers_in_every_recorded_state(
    name: str, call: Callable[[], Awaitable[CapabilityResult]], state: ClusterState
) -> None:
    """Healthy, degraded, unquorate, a node down, and a standalone installation.

    A tool tested only against a healthy cluster is a tool whose behaviour
    during the incident is unknown, which is the whole reason the corpus has
    five states.
    """
    with investigating(state):
        result = await call()

    if result.succeeded:
        assert "undetermined" in result.value
        return
    assert result.error is not None
    assert result.error.message.strip(), f"{name} in {state.value}: failed without saying why"
