"""The container a sandbox runs as: read-only, with two mounts and no more.

Three properties, and each removes a way for one execution to affect the next.

**The root filesystem is read-only.** A capability that writes to
``/usr/lib`` writes nowhere, so nothing it does survives its own container — and
a container image is shared between sandboxes, which is what makes "nothing
survives" matter rather than merely being tidy.

**Scratch is a tmpfs, sized.** In memory rather than on a volume,
because the whole of it disappears when the container does. Sizing it is what
makes the scratch quota enforced by the kernel rather than watched: a write past
``tmpfs``'s size fails, immediately, in the writer.

**Content is bind-mounted read-only.** The same bundle the ``process``
profile writes without a write bit and the ``kubernetes`` profile projects with
``readOnly: true``. Three mechanisms, one digest, and the digest is checked
before every execution — so a mount option that silently did not apply is caught
by the same assertion in all three.

Nothing else is mounted. No Docker socket, no host path, no configuration
directory. A sandbox with the runtime's own socket in it is not a sandbox.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from config.constants.security import (
    SANDBOX_CONTAINER_NAME,
    SANDBOX_CONTENT_MOUNT_PATH,
    SANDBOX_SCRATCH_MOUNT_PATH,
)
from platform.sandbox.spec import ResourceLimits, SandboxSpec


@dataclass(frozen=True, slots=True)
class Mount:
    """One path from the host, and whether the sandbox may write to it."""

    source: str
    target: str
    read_only: bool = True

    def argument(self) -> str:
        """Return this mount as a ``--mount`` value."""
        options = f"type=bind,source={self.source},target={self.target}"
        return options + (",readonly" if self.read_only else "")


@dataclass(frozen=True, slots=True)
class ContainerSpec:
    """Everything the runtime needs to create one sandbox container."""

    name: str
    image: str
    network: str
    limits: ResourceLimits
    environment: Mapping[str, str] = field(default_factory=dict)
    mounts: tuple[Mount, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict)
    scratch_path: str = SANDBOX_SCRATCH_MOUNT_PATH
    content_path: str = SANDBOX_CONTENT_MOUNT_PATH
    read_only_root: bool = True
    container_name: str = SANDBOX_CONTAINER_NAME

    def create_arguments(self) -> tuple[str, ...]:
        """Return the runtime arguments that create this container.

        Ordered so a failed run is readable in a shell history: identity, then
        confinement, then the image. The security flags are not optional and
        there is no parameter that turns one off — a "privileged mode for
        debugging" flag is the flag that is set in production a year later.
        """
        arguments = [
            "create",
            "--name",
            self.name,
            "--network",
            self.network,
            "--read-only" if self.read_only_root else "--read-only",
            "--tmpfs",
            f"{self.scratch_path}:rw,size={self.limits.scratch_bytes},mode=1777",
            "--memory",
            str(self.limits.memory_bytes),
            # Docker takes CPU *quota* as a fraction of a core, not a budget of
            # seconds. One core is the ceiling; the CPU-seconds budget is the
            # sampler's, which is what names the bound when it is crossed.
            "--cpus",
            "1.0",
            "--pids-limit",
            str(self.limits.max_processes),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network-alias",
            self.container_name,
        ]
        for name, value in sorted(self.environment.items()):
            arguments.extend(["--env", f"{name}={value}"])
        for label, value in sorted(self.labels.items()):
            arguments.extend(["--label", f"{label}={value}"])
        for mount in self.mounts:
            arguments.extend(["--mount", mount.argument()])
        arguments.append(self.image)
        # The container has to stay up between executions, because a sandbox
        # outlives one command. The image's own entrypoint is not run: a
        # sandbox is a place to execute capability code, not a service.
        arguments.extend(["sleep", "infinity"])
        return tuple(arguments)


def container_spec(
    sandbox_id: str,
    spec: SandboxSpec,
    *,
    network: str,
    scratch_source: str,
    content_source: str,
    environment: Mapping[str, str],
) -> ContainerSpec:
    """Return the container one sandbox runs as.

    ``scratch_source`` is bind-mounted writable *as well as* the tmpfs being
    sized, because the runner has to be able to read what a capability wrote —
    a scratch mount the host cannot see is a scratch mount whose quota cannot be
    sampled and whose output cannot be collected.
    """
    return ContainerSpec(
        name=f"ninjasre-{sandbox_id}",
        image=spec.image,
        network=network,
        limits=spec.limits,
        environment=environment,
        mounts=(
            Mount(source=scratch_source, target=spec.scratch_path, read_only=False),
            Mount(source=content_source, target=spec.content_path, read_only=True),
        ),
        labels={
            "ninjasre.io/sandbox": sandbox_id,
            "ninjasre.io/org": spec.org_id,
            "ninjasre.io/team": spec.team_id,
            "ninjasre.io/investigation": spec.investigation_id,
            **dict(spec.labels),
        },
        scratch_path=spec.scratch_path,
        content_path=spec.content_path,
    )


__all__ = [
    "ContainerSpec",
    "Mount",
    "container_spec",
]
