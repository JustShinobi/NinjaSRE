"""Three deployment shapes behind one setting, and what each one actually implies.

FR-005 asks that a profile be selectable by a single configuration value and
that it determine the sandbox profile, the proxy's placement, and the
concurrency defaults *consistently*. The second half is the load-bearing one.
Three independent settings would let a deployment be half one shape and half
another — the in-process proxy with cluster concurrency, the process sandbox in
a multi-tenant cluster — and every one of those combinations is untested by
construction, because nobody chose it.

So the profile is the input and the rest is derived. An operator who genuinely
needs the sandbox that does not match their profile can still say so, and the
validator reports the disagreement rather than silently taking one of them.

The container counts are here rather than read from the Compose files because
they are a claim the deployment makes about itself, and
``tests/contract/deployment/`` checks the files against them. Reading the count
from the file would make the file's own drift undetectable.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from config.constants.deployment import (
    DEFAULT_DEPLOYMENT_PROFILE,
    DEPLOYMENT_PROFILE_DEV,
    DEPLOYMENT_PROFILE_ENTERPRISE,
    DEPLOYMENT_PROFILE_STANDARD,
    DEPLOYMENT_PROFILES,
    DEV_GLOBAL_CONCURRENCY,
    DEV_PROFILE_SERVICES,
    DEV_TEAM_CONCURRENCY,
    ENTERPRISE_GLOBAL_CONCURRENCY,
    ENTERPRISE_TEAM_CONCURRENCY,
    IDENTITY_LOCAL_ADMIN,
    IDENTITY_SSO,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    PROXY_DEPLOYMENT_CONTAINER,
    PROXY_DEPLOYMENT_IN_PROCESS,
    PROXY_DEPLOYMENT_SERVICE,
    SCHEDULER_IN_PROCESS,
    SCHEDULER_LEADER_CLAIMED,
    STANDARD_GLOBAL_CONCURRENCY,
    STANDARD_PROFILE_SERVICES,
    STANDARD_TEAM_CONCURRENCY,
)
from platform.sandbox.spec import SandboxProfile
from platform.startup.errors import UnknownDeploymentProfile


class DeploymentProfile(StrEnum):
    """Which of the three shapes this deployment is.

    Not a size. ``standard`` is not "medium ``dev``": it runs the credential
    proxy as its own container and the sandbox in containers, which are
    different trust boundaries rather than more of the same one.
    """

    DEV = DEPLOYMENT_PROFILE_DEV
    STANDARD = DEPLOYMENT_PROFILE_STANDARD
    ENTERPRISE = DEPLOYMENT_PROFILE_ENTERPRISE


@dataclass(frozen=True, slots=True)
class ProfileTopology:
    """Everything one profile decides, in one value.

    ``container_count`` is zero for ``enterprise`` on purpose: a Helm release's
    pod count is a function of its replica settings, and a fixed number here
    would be a claim the chart cannot keep.
    """

    profile: DeploymentProfile
    services: tuple[str, ...]
    container_count: int
    sandbox_profile: SandboxProfile
    proxy_deployment: str
    identity: str
    scheduler: str
    global_concurrency: int
    team_concurrency: int

    @property
    def runs_proxy_in_process(self) -> bool:
        """Return whether the credential proxy shares the application's process."""
        return self.proxy_deployment == PROXY_DEPLOYMENT_IN_PROCESS

    @property
    def container_count_is_fixed(self) -> bool:
        """Return whether this profile has a countable set of containers."""
        return self.container_count > 0

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint or console serves."""
        return {
            "profile": str(self.profile),
            "services": list(self.services),
            "container_count": self.container_count,
            "sandbox_profile": str(self.sandbox_profile),
            "proxy_deployment": self.proxy_deployment,
            "identity": self.identity,
            "scheduler": self.scheduler,
            "global_concurrency": self.global_concurrency,
            "team_concurrency": self.team_concurrency,
        }

    def summary(self) -> str:
        """Return the line a deployment logs at start.

        Names the profile and the two things about it an operator most often
        gets wrong: where the credential proxy is, and which sandbox is
        actually isolating capability execution.
        """
        shape = (
            f"{len(self.services)} containers"
            if self.container_count_is_fixed
            else "Helm-managed replicas"
        )
        return (
            f"deployment profile {self.profile}: {shape}; credential proxy "
            f"{self.proxy_deployment}; sandbox {self.sandbox_profile}; "
            f"concurrency {self.global_concurrency} global / {self.team_concurrency} per team"
        )


_TOPOLOGIES: dict[DeploymentProfile, ProfileTopology] = {
    DeploymentProfile.DEV: ProfileTopology(
        profile=DeploymentProfile.DEV,
        services=DEV_PROFILE_SERVICES,
        container_count=len(DEV_PROFILE_SERVICES),
        sandbox_profile=SandboxProfile.PROCESS,
        proxy_deployment=PROXY_DEPLOYMENT_IN_PROCESS,
        identity=IDENTITY_LOCAL_ADMIN,
        scheduler=SCHEDULER_IN_PROCESS,
        global_concurrency=DEV_GLOBAL_CONCURRENCY,
        team_concurrency=DEV_TEAM_CONCURRENCY,
    ),
    DeploymentProfile.STANDARD: ProfileTopology(
        profile=DeploymentProfile.STANDARD,
        services=STANDARD_PROFILE_SERVICES,
        container_count=len(STANDARD_PROFILE_SERVICES),
        sandbox_profile=SandboxProfile.CONTAINER,
        proxy_deployment=PROXY_DEPLOYMENT_CONTAINER,
        identity=IDENTITY_LOCAL_ADMIN,
        scheduler=SCHEDULER_IN_PROCESS,
        global_concurrency=STANDARD_GLOBAL_CONCURRENCY,
        team_concurrency=STANDARD_TEAM_CONCURRENCY,
    ),
    DeploymentProfile.ENTERPRISE: ProfileTopology(
        profile=DeploymentProfile.ENTERPRISE,
        services=STANDARD_PROFILE_SERVICES,
        container_count=0,
        sandbox_profile=SandboxProfile.KUBERNETES,
        proxy_deployment=PROXY_DEPLOYMENT_SERVICE,
        identity=IDENTITY_SSO,
        scheduler=SCHEDULER_LEADER_CLAIMED,
        global_concurrency=ENTERPRISE_GLOBAL_CONCURRENCY,
        team_concurrency=ENTERPRISE_TEAM_CONCURRENCY,
    ),
}


def resolve_profile(environ: Mapping[str, str] | None = None) -> DeploymentProfile:
    """Return the profile this deployment runs.

    Raises ``UnknownDeploymentProfile`` on a name that is not one of the three.
    """
    source = environ if environ is not None else os.environ
    name = (source.get(NINJASRE_DEPLOYMENT_PROFILE_ENV) or DEFAULT_DEPLOYMENT_PROFILE).strip()
    if name.lower() not in DEPLOYMENT_PROFILES:
        raise UnknownDeploymentProfile(name, DEPLOYMENT_PROFILES)
    return DeploymentProfile(name.lower())


def topology_for(profile: DeploymentProfile) -> ProfileTopology:
    """Return what ``profile`` decides about components, isolation, and bounds."""
    return _TOPOLOGIES[profile]


def resolve_topology(environ: Mapping[str, str] | None = None) -> ProfileTopology:
    """Return the topology this deployment's single profile setting implies."""
    return topology_for(resolve_profile(environ))


__all__ = [
    "DeploymentProfile",
    "ProfileTopology",
    "resolve_profile",
    "resolve_topology",
    "topology_for",
]
