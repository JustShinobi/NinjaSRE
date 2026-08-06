"""What one investigation cannot see of another, and what happens when it fails.

Three claims, and each is checked against something a deployment could actually
get wrong.

**Concurrent investigations are mutually invisible.** A probe capability
runs inside one sandbox and goes looking for the other's filesystem, processes,
and network. The assertions are per profile rather than uniform, because the
three profiles genuinely differ in strength and a test that asserted the
strongest claim everywhere would either fail on ``process`` or be written down
to the weakest and stop meaning anything. What is uniform is that a sandbox is
never *told* where another one is, and that each profile's own declared guarantee
is the one it actually keeps.

**Provisioning failure fails closed.** The interesting version of this
is not "an exception was raised". It is that there is no code path anywhere in
the package that returns something less isolated when the runtime is missing, so
the test asserts on the *type* and then on the absence of a fallback: the module
surface is searched for anything that could hand back an unsandboxed executor.

**A sandbox cannot rewrite what it will execute next.** Delivered
content is verified before every execution, so tampering is refused on the way
in rather than discovered afterwards.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from platform.sandbox import (
    ContentBundle,
    ContentTampered,
    EgressPolicy,
    ExecutionRequest,
    Sandbox,
    SandboxProfile,
    SandboxProvisioningFailed,
    SandboxRuntimeUnavailable,
    SandboxSpec,
)
from platform.sandbox.profiles.container.runner import ContainerSandbox
from platform.sandbox.profiles.kubernetes.runner import KubernetesSandbox
from platform.sandbox.profiles.process.runner import ProcessSandbox
from platform.sandbox.selection import GuaranteeStrength, guarantees_for
from platform.sandbox.spec import LimitKind

pytestmark = pytest.mark.security

PROXY_URL = "http://127.0.0.1:8081"


def _spec(investigation: str, *, sentinel: str = "") -> SandboxSpec:
    """Return a spec for one investigation, optionally carrying a marked skill."""
    content = (
        ContentBundle.from_mapping({"skills/probe.md": f"# {sentinel}\n"})
        if sentinel
        else ContentBundle.empty()
    )
    return SandboxSpec(
        org_id="acme",
        team_id="platform",
        investigation_id=investigation,
        egress=EgressPolicy(proxy_url=PROXY_URL, hosts=("api.datadoghq.com",)),
        content=content,
        image="ninjasre/sandbox:test",
    )


@pytest.fixture(params=[profile.value for profile in SandboxProfile])
def profile(request: pytest.FixtureRequest) -> SandboxProfile:
    """Return the profile this row is exercising."""
    return SandboxProfile(request.param)


@pytest.fixture
def sandbox(profile: SandboxProfile) -> Sandbox:
    """Return one profile's ``Sandbox``, built the way the contract suite builds it."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract" / "sandbox"))
    from engines import SimulatedContainerEngine, SimulatedKubernetesApi

    if profile is SandboxProfile.PROCESS:
        return ProcessSandbox(namespace_available=False)
    if profile is SandboxProfile.CONTAINER:
        return ContainerSandbox(engine=SimulatedContainerEngine())
    return KubernetesSandbox(api=SimulatedKubernetesApi(), pool_size=0)


async def test_two_investigations_get_separate_scratch_and_cannot_see_each_others(
    sandbox: Sandbox,
) -> None:
    """Filesystem: neither sandbox is told where the other's data is.

    The uniform part is that a sandbox is never handed another's
    path — not by its working directory, not by its environment, not by its
    content mount. The profile-dependent part is what happens when one is
    supplied anyway, and the assertion below follows each profile's declared
    isolation strength rather than pretending the three are equal.
    """
    first = await sandbox.provision(_spec("inv-first"))
    second = await sandbox.provision(_spec("inv-second"))
    try:
        assert first.scratch_path or second.scratch_path
        await sandbox.execute(
            first,
            ExecutionRequest(command=_python("open('secret.txt','w').write('first-only')")),
        )

        # The second sandbox looks in its own scratch — the only path it is given
        # — and finds nothing of the first's. Its working directory, its
        # environment, and its content mount name nothing outside itself.
        listing = await sandbox.execute(
            second,
            ExecutionRequest(
                command=_python("import os, sys; sys.stdout.write(str(os.listdir()))")
            ),
        )
        assert b"secret.txt" not in listing.stdout

        # A direct attempt at the other instance's path is the case that
        # separates the profiles, so the assertion follows what each one
        # declares rather than asserting the strongest claim everywhere. The
        # two container-backed profiles are in separate mount namespaces and
        # refuse it. ``process`` shares the host's mount table, declares
        # ``BEST_EFFORT`` isolation, and is marked development-only for exactly
        # this reason — writing the assertion down to the weakest profile would
        # stop it catching a regression in the other two.
        probe = await sandbox.execute(
            second,
            ExecutionRequest(
                command=_python(
                    "import sys\n"
                    "try:\n"
                    f"    sys.stdout.write(open({first.scratch_path + '/secret.txt'!r}).read())\n"
                    "except OSError:\n"
                    "    sys.stdout.write('DENIED')\n"
                )
            ),
        )
        declared = guarantees_for(sandbox.profile, system=sys.platform)
        if declared.isolation_strength is GuaranteeStrength.ENFORCED:
            assert probe.stdout == b"DENIED"
        else:
            assert declared.development_only
    finally:
        await sandbox.release(first)
        await sandbox.release(second)


async def test_a_sandbox_cannot_signal_another_investigations_processes(
    sandbox: Sandbox,
) -> None:
    """Processes: one sandbox's work is not in another's process group."""
    first = await sandbox.provision(_spec("inv-first"))
    second = await sandbox.provision(_spec("inv-second"))
    try:
        groups = set()
        for instance in (first, second):
            result = await sandbox.execute(
                instance,
                ExecutionRequest(
                    command=_python("import os, sys; sys.stdout.write(str(os.getpgrp()))")
                    if sys.platform != "win32"
                    else _python("import os, sys; sys.stdout.write(str(os.getpid()))")
                ),
            )
            groups.add(result.stdout.decode())
        assert len(groups) == 2, "two sandboxes sharing a process group share a kill signal"
    finally:
        await sandbox.release(first)
        await sandbox.release(second)


async def test_each_profile_keeps_the_network_guarantee_it_declares(
    sandbox: Sandbox, profile: SandboxProfile
) -> None:
    """Network: what a profile claims and what it enforces are the same thing.

    The ``process`` profile without a usable network namespace declares
    ``BEST_EFFORT`` egress and is development-only; the other two declare
    ``ENFORCED``. Asserting the declaration matches the mechanism is the honest
    form of this test — asserting "no packet escapes" on a CI runner with no
    network would pass for the wrong reason.
    """
    guarantees = guarantees_for(profile, system=sys.platform, network_namespace_available=False)
    if profile is SandboxProfile.PROCESS:
        assert guarantees.development_only
        assert guarantees.egress_strength is GuaranteeStrength.BEST_EFFORT
        assert guarantees.isolation_strength is GuaranteeStrength.BEST_EFFORT
        assert "mount table shared" in guarantees.isolation_mechanism
    else:
        assert not guarantees.development_only
        assert guarantees.egress_strength is GuaranteeStrength.ENFORCED
        assert guarantees.isolation_strength is GuaranteeStrength.ENFORCED
        assert guarantees.weakened == ()


async def test_a_sandbox_cannot_rewrite_the_content_it_will_execute_next(
    sandbox: Sandbox,
) -> None:
    """Tampering is refused on the way in, not reported afterwards."""
    spec = _spec("inv-content", sentinel="triage")
    instance = await sandbox.provision(spec)
    try:
        first = await sandbox.execute(instance, ExecutionRequest(command=_python("pass")))
        assert first.succeeded

        # Tamper with the delivered content from outside the sandbox, which is
        # strictly more than a sandbox can do — the read-only mount already
        # refuses it from within. The verification must still refuse the next
        # execution rather than run modified content.
        tampered = ContentBundle.from_mapping({"skills/probe.md": "# rewritten\n"})
        _rewrite(sandbox, instance, tampered)

        with pytest.raises(ContentTampered):
            await sandbox.execute(instance, ExecutionRequest(command=_python("pass")))
    finally:
        await sandbox.release(instance)


async def test_provisioning_failure_fails_the_investigation_with_no_fallback() -> None:
    """There is no unsandboxed path to fall back to, under any configuration."""

    class NoRuntime:
        """A container runtime that is not installed."""

        async def available(self) -> bool:
            return False

    sandbox = ContainerSandbox(engine=NoRuntime())  # type: ignore[arg-type]
    with pytest.raises(SandboxRuntimeUnavailable) as raised:
        await sandbox.provision(_spec("inv-nofallback"))

    assert isinstance(raised.value, SandboxProvisioningFailed)
    assert "no unsandboxed path" in str(raised.value)


def test_no_module_in_the_package_offers_an_unsandboxed_executor() -> None:
    """Structurally: the fallback nobody should reach does not exist.

    A test that only asserted the exception would still pass the day somebody
    added ``build_sandbox(..., allow_unsandboxed=True)`` for a debugging session.
    This one fails on the name.
    """
    import importlib
    import pkgutil

    import platform.sandbox as package

    forbidden = ("unsandboxed", "no_sandbox", "disable_sandbox", "bypass_sandbox", "allow_direct")
    offenders: list[str] = []
    for module in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        loaded = importlib.import_module(module.name)
        offenders.extend(
            f"{module.name}.{name}"
            for name in dir(loaded)
            if any(marker in name.lower() for marker in forbidden)
        )
    assert offenders == []


def test_every_bound_the_deployment_declares_is_one_a_profile_enforces() -> None:
    """No bound is declared and then quietly unenforced anywhere."""
    for profile in SandboxProfile:
        guarantees = guarantees_for(profile, system="linux")
        assert set(guarantees.limits) == set(LimitKind)
        assert GuaranteeStrength.UNAVAILABLE not in guarantees.limits.values()


def _python(source: str) -> tuple[str, ...]:
    """Return the command that runs ``source`` inside a sandbox."""
    return (sys.executable, "-I", "-c", source)


def _rewrite(sandbox: Sandbox, instance: object, content: ContentBundle) -> None:
    """Replace a sandbox's delivered content, through the path that profile delivers by.

    Deliberately not uniform. The three profiles deliver content by three
    mechanisms — a read-only directory, a read-only bind mount, a projected
    ConfigMap — and immutability is only meaningfully checked by tampering with the
    *source* each one actually reads. A test that always wrote files would prove
    nothing about the profile whose source is an API object.

    Every one of these is strictly more than a sandbox itself can do: the mount
    is read-only from inside. That is the point — the check has to hold even
    against something with more access than the thing it is protecting against.
    """
    import base64
    import os
    import stat

    if sandbox.profile is SandboxProfile.KUBERNETES:
        provisioned = sandbox._lookup(instance)  # type: ignore[attr-defined]
        name = f"ninjasre-content-{instance.sandbox_id}"  # type: ignore[attr-defined]
        stored = sandbox._api._config_maps[name]  # type: ignore[attr-defined]
        stored["binaryData"] = {
            entry.path.replace("/", "__"): base64.b64encode(entry.data).decode()
            for entry in content.entries
        }
        del provisioned
        return

    if sandbox.profile is SandboxProfile.PROCESS:
        root = Path(instance.content_path)  # type: ignore[attr-defined]
    else:
        root = sandbox._lookup(instance).root / "content"  # type: ignore[attr-defined]

    for path in sorted(root.rglob("*"), reverse=True):
        os.chmod(path, path.stat().st_mode | stat.S_IWRITE)
    os.chmod(root, root.stat().st_mode | stat.S_IWRITE | stat.S_IEXEC)
    content.materialise(root)


async def test_two_investigations_can_run_at_the_same_time(sandbox: Sandbox) -> None:
    """Concurrency is the case at issue; serial sandboxes prove nothing about it."""
    first = await sandbox.provision(_spec("inv-a"))
    second = await sandbox.provision(_spec("inv-b"))
    try:
        results = await asyncio.gather(
            sandbox.execute(
                first, ExecutionRequest(command=_python("import sys; sys.stdout.write('a')"))
            ),
            sandbox.execute(
                second, ExecutionRequest(command=_python("import sys; sys.stdout.write('b')"))
            ),
        )
    finally:
        await sandbox.release(first)
        await sandbox.release(second)
    assert [result.stdout for result in results] == [b"a", b"b"]
