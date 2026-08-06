"""Which profile this deployment runs, and what that profile actually guarantees.

Two jobs, and the second is the one that stops the first being dangerous.

``resolve_profile`` reads one environment variable. It is deployment
configuration and never a per-capability choice, because a matrix of
per-tool isolation is a matrix of behaviours nobody can hold in their head while
an incident is running.

``startup_report`` says out loud what the resolved profile enforces on *this*
operating system, and it is the reason the light profiles are acceptable at all
The Windows ``process`` profile cannot bound CPU time the way POSIX can; a deployment that silently accepted it would be running with a weaker
guarantee than its operator believes. So the guarantee is reported at start,
named per bound, and the report is not something a caller has to ask for twice.

There is no function here that returns an unsandboxed executor, and none that
falls back to a lighter profile when the configured one is unavailable. That is
the same reasoning as the mandatory credential proxy: a fallback is what gets switched on
during an outage and never switched back.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from config.constants.security import (
    DEFAULT_SANDBOX_PROFILE,
    NINJASRE_SANDBOX_PROFILE_ENV,
    SANDBOX_PROFILES,
)
from platform.observability.logging import get_logger
from platform.sandbox.errors import UnknownSandboxProfile
from platform.sandbox.spec import LimitKind, SandboxProfile


class GuaranteeStrength(StrEnum):
    """How well a bound is actually held, as opposed to declared.

    ``ENFORCED`` means the operating system or the runtime refuses to let the
    bound be crossed. ``BEST_EFFORT`` means NinjaSRE watches and kills, which a
    determined capability can outrun for a short window. ``UNAVAILABLE`` means
    the bound is not enforced at all on this host, and saying so is the whole
    point of this enum.
    """

    ENFORCED = "enforced"
    BEST_EFFORT = "best_effort"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProfileGuarantees:
    """What one profile enforces on one operating system.

    ``development_only`` is not a synonym for "weak". It marks the combinations
    whose isolation is adequate for a single-tenant workstation and is not
    adequate for a shared production deployment — and it is reported rather than
    inferred, so nobody has to work out which is which from a table in a
    document they do not have.
    """

    profile: SandboxProfile
    system: str
    limits: Mapping[LimitKind, GuaranteeStrength]
    egress_mechanism: str
    egress_strength: GuaranteeStrength
    #: Whether concurrent sandboxes are in separate filesystem and process
    #: namespaces. ``ENFORCED`` for the two profiles with a container
    #: runtime underneath; ``BEST_EFFORT`` for ``process``, which gives each
    #: sandbox its own session and an unguessable scratch directory but shares
    #: the host's mount table — a process that went looking for another
    #: sandbox's path on the same machine would find it. That is the boundary of
    #: the development profile and the reason it is marked as one.
    isolation_mechanism: str = ""
    isolation_strength: GuaranteeStrength = GuaranteeStrength.ENFORCED
    development_only: bool = False

    @property
    def weakened(self) -> tuple[LimitKind, ...]:
        """Return the bounds this combination does not fully enforce."""
        return tuple(
            limit
            for limit, strength in self.limits.items()
            if strength is not GuaranteeStrength.ENFORCED
        )

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "profile": str(self.profile),
            "system": self.system,
            "limits": {str(limit): str(strength) for limit, strength in self.limits.items()},
            "egress_mechanism": self.egress_mechanism,
            "egress_strength": str(self.egress_strength),
            "isolation_mechanism": self.isolation_mechanism,
            "isolation_strength": str(self.isolation_strength),
            "development_only": self.development_only,
            "weakened": [str(limit) for limit in self.weakened],
        }

    def summary(self) -> str:
        """Return the line a deployment logs at start.

        One line, and it names the weaknesses rather than the strengths. An
        operator scanning a boot log is looking for what is *not* covered, and a
        message that led with what works would bury it.
        """
        head = (
            f"sandbox profile {self.profile} on {self.system}: egress via {self.egress_mechanism}"
        )
        if not self.weakened and not self.development_only:
            return f"{head}; all resource limits enforced"
        gaps = ", ".join(f"{limit} {self.limits[limit]}" for limit in self.weakened)
        isolation = f"; isolation {self.isolation_strength} ({self.isolation_mechanism})"
        marker = " — development only" if self.development_only else ""
        return f"{head}; {gaps or 'limits enforced'}{isolation}{marker}"


def resolve_profile(environ: Mapping[str, str] | None = None) -> SandboxProfile:
    """Return the profile this deployment runs.

    Raises ``UnknownSandboxProfile`` on a name that is not one of the three.
    Deliberately not a fallback to the default: a typo in a production
    deployment's configuration would otherwise start the light profile, and the
    only signal would be a log line nobody read.
    """
    source = environ if environ is not None else os.environ
    name = (source.get(NINJASRE_SANDBOX_PROFILE_ENV) or DEFAULT_SANDBOX_PROFILE).strip().lower()
    if name not in SANDBOX_PROFILES:
        raise UnknownSandboxProfile(name, SANDBOX_PROFILES)
    return SandboxProfile(name)


def guarantees_for(
    profile: SandboxProfile,
    *,
    system: str | None = None,
    network_namespace_available: bool = False,
) -> ProfileGuarantees:
    """Return what ``profile`` enforces on ``system``.

    ``network_namespace_available`` is probed rather than assumed for the
    ``process`` profile: an unprivileged process can only get its own network
    namespace where the kernel allows unprivileged user namespaces, and whether
    it does is a property of the host rather than of the code.
    """
    host = system if system is not None else sys.platform
    if profile is SandboxProfile.PROCESS:
        return _process_guarantees(host, network_namespace_available=network_namespace_available)
    if profile is SandboxProfile.CONTAINER:
        return ProfileGuarantees(
            profile=profile,
            system=host,
            limits=dict.fromkeys(LimitKind, GuaranteeStrength.ENFORCED),
            egress_mechanism="dedicated internal bridge with no default route",
            egress_strength=GuaranteeStrength.ENFORCED,
            isolation_mechanism="container filesystem, process, and network namespaces",
            isolation_strength=GuaranteeStrength.ENFORCED,
        )
    return ProfileGuarantees(
        profile=profile,
        system=host,
        limits=dict.fromkeys(LimitKind, GuaranteeStrength.ENFORCED),
        egress_mechanism="Envoy sidecar allow-list with a NetworkPolicy denying direct egress",
        egress_strength=GuaranteeStrength.ENFORCED,
        isolation_mechanism="pod-per-investigation, read-only root, in-memory scratch",
        isolation_strength=GuaranteeStrength.ENFORCED,
    )


def _process_guarantees(system: str, *, network_namespace_available: bool) -> ProfileGuarantees:
    """Return the ``process`` profile's guarantees, which vary by operating system.

    Windows is the case this function exists for. Job Objects bound memory and
    process count as firmly as POSIX rlimits do; there is no Job Object
    equivalent of ``RLIMIT_CPU``, so CPU time falls back to the same wall-clock
    watchdog everything else uses — which a burst-CPU capability can outrun
    between two polls.
    """
    if system == "win32":
        limits = {
            LimitKind.CPU_SECONDS: GuaranteeStrength.UNAVAILABLE,
            LimitKind.MEMORY_BYTES: GuaranteeStrength.ENFORCED,
            LimitKind.WALL_CLOCK_SECONDS: GuaranteeStrength.BEST_EFFORT,
            LimitKind.SCRATCH_BYTES: GuaranteeStrength.BEST_EFFORT,
            LimitKind.PROCESS_COUNT: GuaranteeStrength.ENFORCED,
        }
    else:
        limits = {
            LimitKind.CPU_SECONDS: GuaranteeStrength.ENFORCED,
            LimitKind.MEMORY_BYTES: GuaranteeStrength.ENFORCED,
            LimitKind.WALL_CLOCK_SECONDS: GuaranteeStrength.BEST_EFFORT,
            LimitKind.SCRATCH_BYTES: GuaranteeStrength.BEST_EFFORT,
            LimitKind.PROCESS_COUNT: GuaranteeStrength.ENFORCED,
        }
    if network_namespace_available:
        mechanism = "loopback-only network namespace, proxy on loopback"
        strength = GuaranteeStrength.ENFORCED
    else:
        mechanism = "proxy-only routing (cooperative)"
        strength = GuaranteeStrength.BEST_EFFORT
    return ProfileGuarantees(
        profile=SandboxProfile.PROCESS,
        system=system,
        limits=limits,
        egress_mechanism=mechanism,
        egress_strength=strength,
        isolation_mechanism="private session and scratch directory; host mount table shared",
        isolation_strength=GuaranteeStrength.BEST_EFFORT,
        development_only=True,
    )


def startup_report(
    profile: SandboxProfile,
    *,
    system: str | None = None,
    network_namespace_available: bool = False,
) -> ProfileGuarantees:
    """Return the guarantees to log at start, and log them.

    Emitting the line here rather than leaving it to each caller is deliberate:
    the requirement is that a weaker guarantee is *reported*, and a report that
    depends on every entry point remembering to print it is a report that one
    of them will not.
    """
    report = guarantees_for(
        profile, system=system, network_namespace_available=network_namespace_available
    )
    get_logger(__name__).info(
        "sandbox.profile.selected",
        summary=report.summary(),
        **{k: v for k, v in report.to_record().items() if k != "limits"},
    )
    return report


__all__ = [
    "GuaranteeStrength",
    "ProfileGuarantees",
    "guarantees_for",
    "resolve_profile",
    "startup_report",
]
