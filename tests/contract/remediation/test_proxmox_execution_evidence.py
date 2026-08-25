"""A hypervisor write, run through the real executor, and what it leaves behind.

The suites beside this one drive the control plane directly, which is where the
refusals and the task handling are decided. This one drives the *executor* — the
same object every other remediation goes through — so the properties asserted
here are the ones that only exist once the write is inside it: the sandbox, the
per-resource lock, and the execution record an incident carries.

Nothing hypervisor-specific was added to the executor to make this work, and
that is the point of the file. If a Proxmox-shaped bypass had been needed
anywhere, it would be visible here as an argument nothing else passes.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from capabilities.tools.remediation import control_plane as binding
from capabilities.tools.remediation import registry as shipped_registry
from capabilities.tools.remediation.proxmox import DECLARATIONS, ProxmoxControlPlane
from capabilities.tools.remediation.proxmox.plane import HypervisorTaskFailed
from capabilities.tools.remediation.proxmox.preconditions import PreconditionRefused, evaluate
from core.capability.metadata import SideEffectLevel
from platform.autonomy.levels import AutonomyLevel
from platform.remediation.execution import (
    ExecutionEnvironment,
    RemediationExecutor,
    TargetLocks,
)
from platform.remediation.models import (
    ExecutionOutcome,
    RemediationAction,
    RemediationTarget,
    RollbackPlan,
    StateSnapshot,
)
from platform.remediation.verification import OutcomeVerification
from tests.support.proxmox import SECONDARY, write_client_for

pytestmark = pytest.mark.contract

EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

GUEST = {"node": SECONDARY, "vmid": 100, "kind": "lxc"}


@dataclass(slots=True)
class RecordingIsolation:
    """A sandbox double that records that it was entered and left."""

    entered: int = 0
    left: int = 0
    profile: str = "process"

    @asynccontextmanager
    async def running(self, action: RemediationAction) -> AsyncIterator[ExecutionEnvironment]:
        """Yield the environment, counting both ends of the block."""
        self.entered += 1
        try:
            yield ExecutionEnvironment(
                sandbox_id=f"sandbox-{action.action_id}", profile=self.profile
            )
        finally:
            self.left += 1


@dataclass(slots=True)
class Harness:
    """Everything one execution needs, assembled the way a deployment assembles it."""

    executor: RemediationExecutor
    plane: ProxmoxControlPlane
    transport: Any
    isolation: RecordingIsolation
    unbind: Any = field(default=None)


@dataclass(slots=True)
class Watched:
    """A control plane that records the boundaries of each change it performs.

    A wrapper rather than a patched method, because the plane is a slotted
    dataclass and cannot be patched — which is the right property for it to have
    and the reason the overlap is observed from outside instead.
    """

    inner: ProxmoxControlPlane
    boundaries: list[str]

    async def read(self, action: RemediationAction) -> Any:
        """Return what the inner plane reads."""
        return await self.inner.read(action)

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> Any:
        """Record when this change started and finished, and perform it."""
        self.boundaries.append(f"enter:{action.action_id}")
        # A yield point inside the block, so two changes that were *not*
        # serialised would interleave here and the assertion would see it.
        await asyncio.sleep(0)
        try:
            return await self.inner.change(action, desired=desired, before=before)
        finally:
            self.boundaries.append(f"leave:{action.action_id}")


def clock() -> datetime:
    """Return the fixed instant this suite runs at."""
    return EPOCH


@pytest.fixture
def bind_plane() -> Iterator[Callable[..., Harness]]:
    """Return a factory for a bound control plane, and unbind whatever it bound.

    A factory rather than a fixture per outcome, because what varies between
    these tests is one string — what the task Proxmox starts reports — and a
    fixture parameterised on that would put the interesting value in the test
    identifier rather than in the test.
    """
    previous = binding.current()
    built: list[Harness] = []

    def build(*, task_exit: str = "OK", responses: Mapping[str, Any] | None = None) -> Harness:
        """Return an executor running against a cluster whose tasks report ``task_exit``."""
        client, transport = write_client_for(
            responses=responses,
            task_exit=task_exit,
            task_log=("starting container", "task finished"),
        )
        plane = ProxmoxControlPlane(client=client, declarations=DECLARATIONS)
        binding.bind(plane)
        registry = shipped_registry()
        isolation = RecordingIsolation()
        found = Harness(
            executor=RemediationExecutor(
                registry=registry,
                isolation=isolation,
                verification=OutcomeVerification(registry=registry, clock=clock),
                locks=TargetLocks(timeout_seconds=0.5),
                clock=clock,
            ),
            plane=plane,
            transport=transport,
            isolation=isolation,
        )
        built.append(found)
        return found

    yield build
    binding.restore(previous)


def an_action(
    capability: str = "proxmox_start_guest", *, action_id: str = "a-1"
) -> RemediationAction:
    """Return the action the executor is driven with."""
    return RemediationAction(
        action_id=action_id,
        capability=capability,
        target=RemediationTarget(identifier="plex", environment="homelab", kind="guest"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ada",
        arguments=dict(GUEST),
        team_node_id="team-homelab",
    )


async def read_before(harness: Harness, action: RemediationAction) -> StateSnapshot:
    """Return the state the approval is granted against."""
    components = harness.executor.registry.get(action.capability)
    return await components.reader.read(action, at=EPOCH)


def a_plan(action: RemediationAction, before: StateSnapshot) -> RollbackPlan:
    """Return the plan the capability itself derives for ``action``."""
    plan = shipped_registry().get(action.capability).generator.plan(action, before=before)
    assert plan is not None
    return plan


# --- Evidence -----------------------------------------------------------------


async def test_the_task_identifier_and_its_log_reach_the_execution_record(
    bind_plane: Callable[..., Harness],
) -> None:
    """What an operator searches the cluster's own task list by, kept where they will look."""
    harness = bind_plane()
    action = an_action()
    before = await read_before(harness, action)

    execution = await harness.executor.execute(action, plan=a_plan(action, before), before=before)

    assert execution.outcome is ExecutionOutcome.SUCCEEDED
    ((result,)) = execution.record.results
    assert "UPID:" in result.detail
    assert "finished OK" in result.detail
    assert "task finished" in result.detail


async def test_the_write_happens_inside_the_sandbox(
    bind_plane: Callable[..., Harness],
) -> None:
    """A capability that could be applied outside one is a capability applied outside one."""
    harness = bind_plane()
    action = an_action()
    before = await read_before(harness, action)

    await harness.executor.execute(action, plan=a_plan(action, before), before=before)

    assert harness.isolation.entered == 1
    assert harness.isolation.left == 1


async def test_a_failed_task_is_recorded_as_a_failure_with_the_providers_own_error(
    bind_plane: Callable[..., Harness],
) -> None:
    """The API call returned 200. The task did not succeed, and that is what is reported."""
    harness = bind_plane(task_exit="storage 'externo-nfs-pve01' is not online")
    action = an_action()
    before = await read_before(harness, action)

    with pytest.raises(HypervisorTaskFailed):
        await harness.executor.execute(action, plan=a_plan(action, before), before=before)

    assert harness.transport.writes, "the write was made; the task is what failed"


async def test_a_failed_task_does_not_report_the_action_as_having_worked(
    bind_plane: Callable[..., Harness],
) -> None:
    """The failure travels out rather than being swallowed into a quiet no-op."""
    harness = bind_plane(task_exit="job errors")
    action = an_action()
    before = await read_before(harness, action)

    with pytest.raises(HypervisorTaskFailed) as failed:
        await harness.executor.execute(action, plan=a_plan(action, before), before=before)

    assert "job errors" in str(failed.value)
    assert "returning success is not the action succeeding" in str(failed.value)


# --- Serialisation ------------------------------------------------------------


async def test_two_incidents_proposing_against_one_guest_do_not_act_concurrently(
    bind_plane: Callable[..., Harness],
) -> None:
    """One guest, two actions, and the second waits rather than overlapping the first.

    Asserted against the *transport*: both writes happened, and the second one
    started after the first had finished. Two concurrent writes against one guest
    is precisely what a Proxmox lock exists to stop, and reaching that state from
    inside this deployment would be reaching it from the one direction the
    hypervisor cannot defend against.
    """
    harness = bind_plane()
    overlapping: list[str] = []
    binding.bind(Watched(inner=harness.plane, boundaries=overlapping))

    first = an_action(action_id="incident-1")
    second = an_action(action_id="incident-2")
    before = await read_before(harness, first)
    await asyncio.gather(
        harness.executor.execute(first, plan=a_plan(first, before), before=before),
        harness.executor.execute(second, plan=a_plan(second, before), before=before),
    )

    assert len(overlapping) == 4
    assert overlapping[0].startswith("enter:")
    assert overlapping[1] == overlapping[0].replace("enter:", "leave:"), (
        f"the second execution started before the first finished: {overlapping}"
    )


LIVE_HOLDER = {
    f"/nodes/{SECONDARY}/lxc/100/status/current": {
        "status": "running",
        "name": "plex",
        "vmid": 100,
        "uptime": 813_244,
        "lock": "backup",
        "ha": {"managed": 0},
    },
    f"/nodes/{SECONDARY}/tasks": [
        {
            "upid": "UPID:pve02:0000B200:0511D700:68943C10:vzdump:100:root@pam:",
            "type": "vzdump",
            "status": "running",
            "starttime": 1_754_802_900,
        }
    ],
}


@pytest.mark.parametrize("level", list(AutonomyLevel), ids=[level.value for level in AutonomyLevel])
async def test_unlocking_a_guest_whose_holder_is_alive_is_refused_at_every_level(
    bind_plane: Callable[..., Harness], level: AutonomyLevel
) -> None:
    """No configured posture reaches this, because the check is below the decision.

    The autonomy resolver decides whether a person is asked. It never decides
    whether the guest is safe to touch, and the level is swept here to say so:
    the refusal is the same at ``propose_only`` and at ``act_and_report``,
    because nothing about it is a function of the level.
    """
    harness = bind_plane(responses=LIVE_HOLDER)
    action = an_action("proxmox_unlock_guest")
    before = await read_before(harness, action)

    with pytest.raises(PreconditionRefused) as refused:
        await harness.executor.execute(
            action,
            plan=a_plan(action, before),
            before=before,
            autonomous=level.acts,
        )

    assert "holding_task_dead" in refused.value.names
    assert harness.transport.writes == []


def test_the_precondition_evaluation_cannot_be_told_an_autonomy_level() -> None:
    """Structural, so the sweep above cannot be made vacuous by a later parameter."""
    parameters = set(inspect.signature(evaluate).parameters)

    assert parameters == {"declared", "facts", "before"}


async def test_the_hypervisor_writes_run_through_the_same_executor_as_everything_else(
    bind_plane: Callable[..., Harness],
) -> None:
    """No hypervisor-specific execution path exists, and this is what says so."""
    bind_plane()
    registry = shipped_registry()

    for name in DECLARATIONS:
        assert registry.has(name), name
        components = registry.get(name)
        assert components.reader is not None
        assert components.applier is not None
        assert components.generator is not None
        assert components.verifier is not None
