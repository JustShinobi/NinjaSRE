"""Runs the whole sandbox contract suite once per profile.

Three rows, and every test below runs on all three. That is the claim this
feature makes — a capability behaves identically wherever a deployment runs it — and
this file is the mechanism that makes the claim checkable rather than intended.
A capability that passes on ``process`` and fails on ``kubernetes`` is a gap in
this suite, treated as a bug in the suite.

**The container and Kubernetes rows drive simulated runtimes.** ``engines.py``
implements the ``ContainerEngine`` and ``KubernetesApi`` ports over the same
process-execution core the ``process`` profile uses, layering on the semantics
that make each profile what it is: a read-only root that refuses writes outside
the scratch mount, a bridge with no default route, an Envoy allow-list. They
model the runtime, not the profile — every line of ``profiles/container`` and
``profiles/kubernetes`` under test is the real one.

That is a real limit and worth stating plainly: this suite proves the profiles
behave identically and that each builds the right manifests and argument
vectors. It does not prove Docker and Kubernetes honour those, which is what a
cluster in ``tests/e2e`` is for. The alternative — no suite at all without a
daemon — would mean the two profiles most deployments run were the two nobody
ran on a pull request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
from engines import SimulatedContainerEngine, SimulatedKubernetesApi

from platform.sandbox import (
    ContentBundle,
    EgressPolicy,
    ResourceLimits,
    Sandbox,
    SandboxProfile,
    SandboxSpec,
)
from platform.sandbox.profiles.container.runner import ContainerSandbox
from platform.sandbox.profiles.kubernetes.runner import KubernetesSandbox
from platform.sandbox.profiles.process.runner import ProcessSandbox
from platform.sandbox.trace import CollectingSandboxEvents

PRIMARY_ORG = "acme"
PRIMARY_TEAM = "platform"

#: The proxy every spec routes through. Loopback because that is the local
#: development case, and because it is the one that lets the ``process`` profile
#: reach its stronger egress mechanism where the kernel allows it.
PROXY_URL = "http://127.0.0.1:8081"

#: A vendor the team has configured, and one it has not. The second is the whole
#: of the egress assertion: it is a host no injection rule declares.
ALLOWED_HOST = "api.datadoghq.com"
UNLISTED_HOST = "attacker.example"


@pytest.fixture(params=[profile.value for profile in SandboxProfile])
def profile(request: pytest.FixtureRequest) -> SandboxProfile:
    """Return the profile this row of the suite is exercising."""
    return SandboxProfile(request.param)


@pytest.fixture
def events() -> CollectingSandboxEvents:
    """Return the sink every profile records lifecycle events into."""
    return CollectingSandboxEvents()


@pytest.fixture
async def sandbox(
    profile: SandboxProfile, events: CollectingSandboxEvents
) -> AsyncIterator[Sandbox]:
    """Return one profile's ``Sandbox``, released whatever the test did."""
    built: Sandbox
    if profile is SandboxProfile.PROCESS:
        # Pinned rather than probed. Whether this host allows an unprivileged
        # network namespace is a property of the CI runner, and a suite whose
        # assertions changed with it would be a suite that proved nothing on
        # the machine it failed on. The namespace path has its own test.
        built = ProcessSandbox(events=events, namespace_available=False)
    elif profile is SandboxProfile.CONTAINER:
        built = ContainerSandbox(engine=SimulatedContainerEngine(), events=events)
    else:
        built = KubernetesSandbox(api=SimulatedKubernetesApi(), events=events, pool_size=0)
    yield built


@pytest.fixture
def make_spec() -> Callable[..., SandboxSpec]:
    """Return a factory for specs, so a test states only what it is about."""

    def factory(
        *,
        investigation_id: str = "inv-1",
        limits: ResourceLimits | None = None,
        content: ContentBundle | None = None,
        ttl_seconds: int = 900,
        hosts: tuple[str, ...] = (ALLOWED_HOST,),
    ) -> SandboxSpec:
        return SandboxSpec(
            org_id=PRIMARY_ORG,
            team_id=PRIMARY_TEAM,
            investigation_id=investigation_id,
            egress=EgressPolicy(proxy_url=PROXY_URL, hosts=hosts),
            limits=limits if limits is not None else ResourceLimits.defaults(),
            content=content if content is not None else ContentBundle.empty(),
            ttl_seconds=ttl_seconds,
            image="ninjasre/sandbox:test",
        )

    return factory


@pytest.fixture
def spec(make_spec: Callable[..., SandboxSpec]) -> SandboxSpec:
    """Return the default spec: deployment limits, one allow-listed vendor."""
    return make_spec()
