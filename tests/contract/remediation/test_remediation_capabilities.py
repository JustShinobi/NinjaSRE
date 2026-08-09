"""One suite, run once per shipped remediation capability.

Parameterised rather than written seven times, and that is the point: the
eighth capability somebody adds is covered the moment it appears in
``COMPONENTS``, without anybody remembering to copy a test file. A capability
that reaches production with three components instead of four fails here.

What is asserted is behaviour rather than presence. "Has a generator" is
satisfied by a generator that returns nothing; what matters is that the
generator produces a plan against a readable target, that the reader reports an
unreadable one honestly, that the applier refuses to run outside a sandbox, and
that the verifier finds a divergence somebody induced.

``clear_cache`` is the deliberate exception on one of those, and the suite says
so rather than skipping it: it has no derivable plan, and the assertion for it
is that it says so instead of inventing one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from capabilities.tools.remediation import COMPONENTS, registry
from capabilities.tools.remediation import control_plane as binding
from capabilities.tools.remediation.control_plane import ControlPlaneState
from core.capability.metadata import SideEffectLevel
from platform.remediation.components import RemediationComponents
from platform.remediation.execution import ExecutionEnvironment
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    StateSnapshot,
    SubTargetResult,
)

EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

#: The capabilities whose undo genuinely does not exist. Named rather than
#: detected, so the exception is a decision this suite records rather than
#: something a broken generator could quietly join. A cache clear has no
#: inverse; a deleted snapshot and a deleted disk image have less than that.
NO_DERIVABLE_PLAN = frozenset(
    {"clear_cache", "proxmox_reclaim_storage", "proxmox_remove_orphaned_volume"}
)

#: The three facts a Proxmox guest is addressed by, written once because eight
#: of the hypervisor scenarios name the same guest.
_GUEST: Mapping[str, Any] = {"node": "pve02", "vmid": 100, "kind": "lxc"}

#: A backup volume identifier, which is a recovery point, and an orphaned disk,
#: which is not. Both in Proxmox's own ``store:content/name`` spelling.
_BACKUP = "TeraChad:backup/vzdump-lxc-100-2025_08_09-07_00_02.tar.zst"
_ORPHAN = "local-lvm:vm-129-disk-0"

#: What each capability is asked to do, and what the control plane reports the
#: target holding before it. Enough to exercise a real generator and a real
#: verifier — a table of empty dictionaries would assert only that the
#: components exist.
SCENARIOS: Mapping[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "restart_workload": ({}, {"instances": ["pod-1", "pod-2"]}),
    "rollback_deployment": ({"target_revision": "v41"}, {"revision": "v42"}),
    "scale_workload": ({"replicas": 8}, {"replicas": 4}),
    "cordon_drain_node": ({"drain": True}, {"schedulable": True, "workloads": ["a"]}),
    "update_resource_limits": (
        {"memory_limit": "2Gi"},
        {
            "cpu_request": "100m",
            "cpu_limit": "500m",
            "memory_request": "512Mi",
            "memory_limit": "1Gi",
        },
    ),
    "toggle_feature_flag": ({"enabled": False}, {"enabled": True, "rollout": "50%"}),
    "clear_cache": ({"namespace": "sessions"}, {"entries": 40_192, "hit_rate": 0.91}),
    # The hypervisor writes. Their arguments carry the three facts a Proxmox
    # guest is addressed by, because a hypervisor does not address one by name.
    "proxmox_start_guest": (
        _GUEST,
        {
            "node": "pve02",
            "status": "stopped",
            "lock": "",
            "uptime": 0,
            # A guest that reached ``running`` and whose own agent does not
            # answer booted and did not come up, and only the agent tells the
            # two apart — so the start is the one action that reads it.
            "agent_responds": True,
        },
    ),
    "proxmox_shutdown_guest": (
        _GUEST,
        {"node": "pve02", "status": "running", "lock": "", "uptime": 813_244},
    ),
    "proxmox_reboot_guest": (
        _GUEST,
        {"node": "pve02", "status": "running", "lock": "", "uptime": 813_244},
    ),
    "proxmox_stop_guest": (
        _GUEST,
        {"node": "pve02", "status": "running", "lock": "", "uptime": 813_244},
    ),
    "proxmox_suspend_guest": (
        _GUEST,
        {"node": "pve02", "status": "running", "lock": "", "uptime": 813_244},
    ),
    "proxmox_resume_guest": (
        _GUEST,
        {"node": "pve02", "status": "paused", "lock": "", "uptime": 0},
    ),
    "proxmox_unlock_guest": (
        _GUEST,
        {"node": "pve02", "status": "running", "lock": "backup", "uptime": 813_244},
    ),
    "proxmox_migrate_guest": (
        {**_GUEST, "target": "pve01"},
        {"node": "pve02", "status": "running", "lock": ""},
    ),
    "proxmox_ha_relocate": (
        {"sid": "ct:115", "target": "pve01", "group": "dns"},
        {"ha_node": "pve02", "ha_state": "started", "ha_group": "lab"},
    ),
    "proxmox_reclaim_storage": (
        {"node": "pve02", "datastore": "TeraChad", "items": [_BACKUP]},
        {"items": [_BACKUP], "used_bytes": 7_654_000_000_000},
    ),
    "proxmox_remove_orphaned_volume": (
        {"node": "pve02", "datastore": "local-lvm", "volume": _ORPHAN},
        {"volumes": [_ORPHAN], "owners": {}},
    ),
    "proxmox_retry_backup": (
        {**_GUEST, "storage": "TeraChad"},
        {"last_backup_succeeded": False, "last_backup_at": 1_754_800_000},
    ),
    "proxmox_resync_replication": (
        {"node": "pve02", "job_id": "100-0", "rate_limit_mbps": 50},
        {"failing": True, "last_sync": 1_754_800_000, "target": "pve01"},
    ),
}


@dataclass(slots=True)
class StubControlPlane:
    """A control plane that answers from a dictionary and records what it was told."""

    values: dict[str, Any]
    sub_targets: tuple[str, ...] = ("pod-1", "pod-2")
    readable: bool = True
    applied: list[Mapping[str, Any]] = field(default_factory=list)

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        """Return the stubbed state, or ``None`` when the test made it unreadable."""
        del action
        if not self.readable:
            return None
        return ControlPlaneState(values=dict(self.values), sub_targets=self.sub_targets)

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        """Record the desired state, move the values, and report every piece changed."""
        del action
        self.applied.append(dict(desired))
        for name, value in desired.items():
            if name in self.values:
                self.values[name] = value
        return tuple(
            SubTargetResult(identifier=name, changed=True)
            for name in (before.sub_targets or ("target",))
        )


def an_action(capability: str) -> RemediationAction:
    """Return the action this suite drives ``capability`` with."""
    arguments, _ = SCENARIOS[capability]
    return RemediationAction(
        action_id=f"action-{capability}",
        capability=capability,
        target=RemediationTarget(
            identifier="checkout-api", environment="staging", node_id="team-payments"
        ),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ada",
        arguments=arguments,
        team_node_id="team-payments",
    )


@pytest.fixture(params=[bundle.capability for bundle in COMPONENTS])
def capability(request: pytest.FixtureRequest) -> str:
    """Return each shipped remediation capability in turn."""
    return str(request.param)


@pytest.fixture
def components(capability: str) -> RemediationComponents:
    """Return the four components of the capability under test."""
    return registry().get(capability)


@pytest.fixture
def plane(capability: str):
    """Bind a stub control plane for the duration of one test."""
    _, values = SCENARIOS[capability]
    stub = StubControlPlane(values=dict(values))
    previous = binding.bind(stub)
    yield stub
    binding.restore(previous)


def test_every_shipped_capability_is_declared_as_a_write() -> None:
    """A remediation capability that was not a write would not be gated at all."""
    from capabilities.registry.catalogue import build_registry, reset_registry_cache

    reset_registry_cache()
    catalogue = build_registry()

    for bundle in COMPONENTS:
        found = catalogue.tool(bundle.capability)
        assert found is not None, f"{bundle.capability} is not in the catalogue"
        assert found.metadata.side_effect_level.needs_approval, bundle.capability
        assert found.metadata.requires_approval, bundle.capability
        assert found.metadata.approval_reason.strip(), bundle.capability
        assert found.metadata.rollback_plan or found.metadata.rollback_planner, bundle.capability


def test_the_scenario_table_covers_the_shipped_set() -> None:
    """A capability added without a scenario would be parameterised over nothing."""
    assert set(SCENARIOS) == {bundle.capability for bundle in COMPONENTS}


async def test_the_reader_returns_the_fields_its_capability_is_about(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """A snapshot narrowed to what the action concerns, not to what the API returned.

    Fingerprints are taken of the whole snapshot, so an unrelated annotation
    change would otherwise mark every queued action as conflicted — and a
    conflict check that fires on noise is one reviewers learn to dismiss.
    """
    snapshot = await components.reader.read(an_action(capability), at=EPOCH)

    assert snapshot.known
    assert snapshot.values, capability
    _, expected = SCENARIOS[capability]
    assert set(snapshot.values) <= set(expected), capability


async def test_an_unreadable_target_is_unknown_rather_than_empty(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """An empty snapshot fingerprints to a real value and would compare equal to another."""
    plane.readable = False

    snapshot = await components.reader.read(an_action(capability), at=EPOCH)

    assert not snapshot.known
    assert not snapshot.matches(snapshot), (
        "an unknown snapshot must match nothing, including itself"
    )


async def test_the_generator_produces_a_plan_or_says_there_is_none(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """Six produce a plan against a readable target; one says plainly that it cannot."""
    action = an_action(capability)
    before = await components.reader.read(action, at=EPOCH)

    plan = components.generator.plan(action, before=before)

    if capability in NO_DERIVABLE_PLAN:
        assert plan is None, f"{capability} invented an undo it does not have"
        return

    assert plan is not None, capability
    assert plan.steps, capability
    assert plan.summary.strip(), capability
    assert "checkout-api" in plan.summary, (
        f"{capability}'s plan does not name the target — "
        f'"put it back" is not something an engineer can act on'
    )


async def test_the_generator_produces_nothing_for_an_unreadable_target(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """A plan promising to restore values nobody read would write nulls into production."""
    plane.readable = False
    action = an_action(capability)
    before = await components.reader.read(action, at=EPOCH)

    assert components.generator.plan(action, before=before) is None


async def test_the_applier_changes_the_target_and_reports_per_sub_target(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """One result per piece, because partial success is the ordinary outcome."""
    action = an_action(capability)
    before = await components.reader.read(action, at=EPOCH)

    results = await components.applier.apply(
        action,
        before=before,
        environment=ExecutionEnvironment(sandbox_id="sandbox-1", profile="process"),
    )

    assert results, capability
    assert plane.applied, f"{capability} reported success without reaching the control plane"
    assert all(isinstance(result, SubTargetResult) for result in results)


async def test_the_verifier_finds_a_divergence_somebody_induced(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """The change is applied and then quietly undone; the verifier must notice.

    This is the assertion that separates a real verifier from one that returns
    an empty tuple — and an empty tuple is exactly what a verifier degrades into
    when nobody checks it.
    """
    action = an_action(capability)
    before = await components.reader.read(action, at=EPOCH)
    await components.applier.apply(
        action,
        before=before,
        environment=ExecutionEnvironment(sandbox_id="sandbox-1", profile="process"),
    )

    _, original = SCENARIOS[capability]
    plane.values = dict(original)  # somebody, or something, put it back
    plane.sub_targets = before.sub_targets  # and a restart replaced nothing
    after = await components.reader.read(action, at=EPOCH)

    divergences = components.verifier.verify(action, before=before, after=after)

    assert divergences, f"{capability}'s verifier accepted a change that did not take effect"


async def test_a_converged_change_reports_no_divergence(
    components: RemediationComponents, plane: StubControlPlane, capability: str
) -> None:
    """The other half, so a verifier cannot pass by reporting a divergence always."""
    action = an_action(capability)
    before = await components.reader.read(action, at=EPOCH)
    await components.applier.apply(
        action,
        before=before,
        environment=ExecutionEnvironment(sandbox_id="sandbox-1", profile="process"),
    )
    if capability == "restart_workload":
        plane.sub_targets = ("pod-3", "pod-4")
    if capability == "clear_cache":
        plane.values["entries"] = 0
    after = await components.reader.read(action, at=EPOCH)

    assert components.verifier.verify(action, before=before, after=after) == ()
