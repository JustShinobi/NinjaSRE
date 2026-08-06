"""Shared fixtures for the remediation suite.

Everything is a real object except the control plane and the isolation, and both
are doubles for the same reason: this suite is about what NinjaSRE does *around*
a production change, and a real Kubernetes API would make every assertion here
also an assertion about Kubernetes.

The control plane records what it was asked to change. That recording is what
the no-bypass assertions are made against — a write that reached the target
without an approval shows up as a call this object received, and no amount of
careful reading of the gate proves the same thing.

The isolation double records that it was entered and left. FR-015 says execution
runs inside the sandbox profile, and the way to hold that to account in a unit
test is to assert the applier never ran outside the block.

The helpers are fixtures rather than importable functions on purpose. ``tests/``
is not a package, and a second suite reaching in here by module path would work
only until somebody moved a directory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.capability.metadata import SideEffectLevel
from platform.remediation.components import ComponentRegistry, RemediationComponents
from platform.remediation.execution import (
    ExecutionEnvironment,
    RemediationExecutor,
    TargetLocks,
)
from platform.remediation.models import (
    Divergence,
    RemediationAction,
    RemediationEvidence,
    RemediationTarget,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
    SubTargetResult,
)
from platform.remediation.rollback.generator import PlanFactory
from platform.remediation.verification import OutcomeVerification, divergences_between

ORG = "acme"
TEAM = "team-payments"
REQUESTER = "ada"
REVIEWER = "grace"

WORKLOAD = "checkout-api"
STAGING = "staging"
PRODUCTION = "production"

#: A fixed instant, so an expiry assertion is arithmetic rather than a race.
EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

#: The capability every test in this suite drives unless it says otherwise. A
#: scale, because it is the one whose rollback is a value to restore — which is
#: the shape five of the seven shipped capabilities have.
SCALE = "scale_workload"

#: The one with no derivable rollback, for the waiver path.
CLEAR = "clear_cache"


class FrozenClock:
    """A clock a test moves on purpose."""

    def __init__(self, at: datetime = EPOCH) -> None:
        self.at = at

    def __call__(self) -> datetime:
        """Return the instant this clock is currently at."""
        return self.at

    def advance(self, **delta: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.at += timedelta(**delta)
        return self.at


@dataclass(slots=True)
class RecordingControlPlane:
    """A target that remembers what was applied to it, and what it looks like now.

    ``values`` is what the target reads as. A test assigns to it directly to
    stand for somebody else changing the same workload between the request and
    the execution, and sets ``readable`` to ``False`` to stand for a control
    plane that cannot answer — the two situations the fingerprint and the
    ``known`` flag exist to notice.
    """

    values: dict[str, Any] = field(default_factory=lambda: {"replicas": 4})
    sub_targets: tuple[str, ...] = ("pod-1", "pod-2", "pod-3")
    readable: bool = True
    #: How many sub-targets a change actually moves. Lower than the total is a
    #: partial success, which is the ordinary outcome of acting on a live system.
    changes: int | None = None
    #: How many reads succeed before the control plane stops answering. Set to
    #: one to stand for the case that matters most: the state was readable when
    #: the action was proposed and is not when it is verified.
    readable_reads: int | None = None
    reads: int = 0
    applied: list[Mapping[str, Any]] = field(default_factory=list)

    async def read(self, action: RemediationAction, *, at: datetime) -> StateSnapshot:
        """Return the target's observed state, or the snapshot that says it is unknown."""
        self.reads += 1
        if not self.readable or (
            self.readable_reads is not None and self.reads > self.readable_reads
        ):
            return StateSnapshot.unreadable(str(action.target), at=at)
        return StateSnapshot(
            target=str(action.target),
            observed_at=at,
            values=dict(self.values),
            sub_targets=self.sub_targets,
        )

    async def apply(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        environment: Any,
    ) -> tuple[SubTargetResult, ...]:
        """Record the change, move the state, and report one result per sub-target."""
        assert isinstance(environment, ExecutionEnvironment), (
            "an applier must never run outside a provisioned sandbox"
        )
        self.applied.append(dict(action.arguments))
        moved = self.changes if self.changes is not None else len(before.sub_targets)
        for name, value in action.arguments.items():
            if name in self.values:
                self.values[name] = value
        return tuple(
            SubTargetResult(identifier=name, changed=position < moved)
            for position, name in enumerate(before.sub_targets)
        )

    @property
    def was_applied(self) -> bool:
        """Return whether anything reached the target at all."""
        return bool(self.applied)


@dataclass(slots=True)
class ScaleGenerator:
    """The rollback generator for the capability this suite drives."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the plan restoring the recorded replica count, per sub-target."""
        if not before.known:
            return None
        recorded = before.values.get("replicas")
        return RollbackPlan(
            plan_id="",
            action_id=action.action_id,
            target=str(action.target),
            recorded_state=before,
            summary=f"Scale {action.target.identifier} back to {recorded} replica(s).",
            steps=tuple(
                RollbackStep(
                    ordinal=position,
                    description=f"Restore {name} to {recorded}",
                    capability=SCALE,
                    arguments={"replicas": recorded},
                    sub_target=name,
                )
                for position, name in enumerate(before.sub_targets, start=1)
            ),
        )


@dataclass(slots=True)
class ScaleVerifier:
    """Compares the replica count against the one the action asked for."""

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return the divergence between the intended replica count and the actual one."""
        del before
        return divergences_between({"replicas": action.arguments.get("replicas")}, after.values)


@dataclass(slots=True)
class NoPlanGenerator:
    """The generator for the capability whose undo is not derivable."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return ``None``: nothing puts a cleared cache back."""
        del action, before
        return None


@dataclass(slots=True)
class RecordingIsolation:
    """A sandbox double that records that it was entered and left.

    Asserting on ``entered`` is how this suite holds "execution runs inside the
    sandbox profile" to account without provisioning a container.
    """

    entered: int = 0
    left: int = 0
    profile: str = "process"

    @asynccontextmanager
    async def running(self, action: RemediationAction) -> AsyncIterator[ExecutionEnvironment]:
        """Yield the environment, counting both ends of the block."""
        self.entered += 1
        try:
            yield ExecutionEnvironment(
                sandbox_id=f"sandbox-{self.entered}",
                profile=self.profile,
                proxy_url="http://credential-proxy.internal",
                scratch_path="/scratch",
            )
        finally:
            self.left += 1


@dataclass(slots=True)
class RecordingStepRunner:
    """Runs rollback steps by writing their arguments back to the control plane."""

    plane: RecordingControlPlane
    ran: list[RollbackStep] = field(default_factory=list)
    fail_at: int | None = None

    async def run(self, step: RollbackStep, *, action: RemediationAction) -> SubTargetResult:
        """Apply one step, or raise when the test asked this ordinal to fail."""
        del action
        if self.fail_at is not None and step.ordinal == self.fail_at:
            raise RuntimeError(f"step {step.ordinal} could not be applied")
        self.ran.append(step)
        for name, value in step.arguments.items():
            if name in self.plane.values:
                self.plane.values[name] = value
        return SubTargetResult(identifier=step.sub_target or step.capability, changed=True)


@dataclass(slots=True)
class RecordingNotifier:
    """Remembers which autonomous executions a team was told about."""

    told: list[str] = field(default_factory=list)

    async def autonomous_execution(self, action: RemediationAction, record: Any) -> None:
        """Record that the team was told."""
        del record
        self.told.append(action.action_id)


@pytest.fixture
def clock() -> FrozenClock:
    """Return a clock the test moves."""
    return FrozenClock()


@pytest.fixture
def plane() -> RecordingControlPlane:
    """Return the target double every action in this suite is applied to."""
    return RecordingControlPlane()


@pytest.fixture
def isolation() -> RecordingIsolation:
    """Return the sandbox double every execution runs inside."""
    return RecordingIsolation()


@pytest.fixture
def registry(plane: RecordingControlPlane) -> ComponentRegistry:
    """Return a registry holding one reversible capability and one that is not."""
    return ComponentRegistry().register_all(
        (
            RemediationComponents(
                capability=SCALE,
                reader=plane,
                applier=plane,
                generator=ScaleGenerator(),
                verifier=ScaleVerifier(),
            ),
            RemediationComponents(
                capability=CLEAR,
                reader=plane,
                applier=plane,
                generator=NoPlanGenerator(),
                verifier=ScaleVerifier(),
            ),
        )
    )


@pytest.fixture
def plans(registry: ComponentRegistry, clock: FrozenClock) -> PlanFactory:
    """Return a plan factory with deterministic identifiers."""
    counter = {"n": 0}

    def identify() -> str:
        counter["n"] += 1
        return f"plan-{counter['n']}"

    return PlanFactory(registry=registry, clock=clock, identifiers=identify)


@pytest.fixture
def verification(registry: ComponentRegistry, clock: FrozenClock) -> OutcomeVerification:
    """Return the post-execution verification wired to the same reader."""
    return OutcomeVerification(registry=registry, clock=clock)


@pytest.fixture
def executor(
    registry: ComponentRegistry,
    isolation: RecordingIsolation,
    verification: OutcomeVerification,
    clock: FrozenClock,
) -> RemediationExecutor:
    """Return an executor with no allow-list and no kill switch engaged."""
    return RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )


@pytest.fixture
def notifier() -> RecordingNotifier:
    """Return the surface an autonomous execution is announced on."""
    return RecordingNotifier()


@pytest.fixture
def step_runner(plane: RecordingControlPlane) -> Callable[..., RecordingStepRunner]:
    """Return a builder for the runner that applies a rollback plan's steps."""

    def build(*, fail_at: int | None = None) -> RecordingStepRunner:
        return RecordingStepRunner(plane=plane, fail_at=fail_at)

    return build


@pytest.fixture
def an_action() -> Callable[..., RemediationAction]:
    """Return a builder for the action a test proposes."""

    def build(
        capability: str = SCALE,
        *,
        action_id: str = "action-1",
        identifier: str = WORKLOAD,
        environment: str = STAGING,
        level: SideEffectLevel = SideEffectLevel.WRITE_REVERSIBLE,
        arguments: Mapping[str, Any] | None = None,
        evidence: Sequence[str] = ("memory rose steadily for 40 minutes",),
        team_node_id: str | None = TEAM,
        requester: str = REQUESTER,
    ) -> RemediationAction:
        return RemediationAction(
            action_id=action_id,
            capability=capability,
            target=RemediationTarget(
                identifier=identifier,
                environment=environment,
                node_id=team_node_id,
            ),
            side_effect_level=level,
            requester=requester,
            intent=f"{capability} on {identifier}",
            arguments=dict(arguments) if arguments is not None else {"replicas": 8},
            evidence=tuple(RemediationEvidence(summary=item) for item in evidence),
            run_id="run-1",
            team_node_id=team_node_id,
        )

    return build
