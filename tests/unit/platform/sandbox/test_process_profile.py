"""The `process` profile's own machinery: sampling, limits, and egress planning.

The contract suite exercises this profile end to end. What it does not reach is
the platform-specific interior — the ``/proc`` reader, the rlimit backstops, the
namespace probe — and those are where a change silently stops enforcing
something, because they fail by reporting less rather than by raising.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from config.constants.security import (
    SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS,
    SANDBOX_HTTP_PROXY_ENV,
    SANDBOX_HTTPS_PROXY_ENV,
    SANDBOX_KERNEL_BACKSTOP_FACTOR,
    SANDBOX_NO_PROXY_ENV,
)
from platform.sandbox import EgressPolicy, LimitKind, ResourceLimits
from platform.sandbox.profiles.process.monitor import (
    ProcResourceMonitor,
    ResourceSample,
    ScratchOnlyMonitor,
    default_monitor,
    directory_bytes,
)
from platform.sandbox.profiles.process.network import plan_egress
from platform.sandbox.selection import GuaranteeStrength

pytestmark = pytest.mark.unit

LOOPBACK_PROXY = "http://127.0.0.1:8081"
REMOTE_PROXY = "https://proxy.internal:8443"


def test_a_sample_names_the_first_bound_it_crosses() -> None:
    limits = ResourceLimits(
        cpu_seconds=10, memory_bytes=1_000, scratch_bytes=1_000, max_processes=4
    )
    assert ResourceSample(memory_bytes=2_000).exceeded(limits) is LimitKind.MEMORY_BYTES
    assert ResourceSample(scratch_bytes=2_000).exceeded(limits) is LimitKind.SCRATCH_BYTES
    assert ResourceSample(process_count=9).exceeded(limits) is LimitKind.PROCESS_COUNT
    assert ResourceSample(cpu_seconds=11.0).exceeded(limits) is LimitKind.CPU_SECONDS
    assert ResourceSample(cpu_seconds=1.0, memory_bytes=10).exceeded(limits) is None


def test_a_counter_this_host_cannot_read_is_not_treated_as_zero() -> None:
    """Reading an unavailable counter as zero is how a bound stops being checked."""
    limits = ResourceLimits(memory_bytes=1, max_processes=1, cpu_seconds=1)
    unreadable = ResourceSample(scratch_bytes=0)
    assert unreadable.cpu_seconds is None
    assert unreadable.memory_bytes is None
    assert unreadable.exceeded(limits) is None


def test_the_scratch_walk_totals_a_nested_tree(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.bin").write_bytes(b"x" * 1_000)
    (tmp_path / "nested" / "b.bin").write_bytes(b"y" * 2_000)
    assert directory_bytes(tmp_path) == 3_000


def test_the_scratch_walk_of_a_directory_that_vanished_is_not_an_error(tmp_path: Path) -> None:
    """Release looks exactly like this from the sampler's point of view."""
    assert directory_bytes(tmp_path / "gone") == 0


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("linux", "ProcResourceMonitor"),
        ("win32", "ScratchOnlyMonitor"),
        ("darwin", "PsResourceMonitor"),
    ],
)
def test_each_host_gets_the_reader_that_works_on_it(system: str, expected: str) -> None:
    assert type(default_monitor(system=system)).__name__ == expected


def test_a_scratch_only_monitor_still_reports_the_quota(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    sample = ScratchOnlyMonitor().sample(pid=1, scratch=tmp_path)
    assert sample.scratch_bytes == 10
    assert sample.cpu_seconds is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
def test_the_proc_reader_sees_this_processs_own_group(tmp_path: Path) -> None:
    import os

    sample = ProcResourceMonitor().sample(pid=os.getpgrp(), scratch=tmp_path)
    assert sample.process_count is not None and sample.process_count >= 1
    assert sample.memory_bytes is not None and sample.memory_bytes > 0
    assert sample.cpu_seconds is not None and sample.cpu_seconds >= 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rlimits")
def test_the_kernel_backstop_sits_above_the_bound_the_sampler_holds() -> None:
    """If the kernel killed first, nothing could name the bound that was crossed."""
    import os
    import resource

    from platform.sandbox.profiles.process.limits_posix import apply_limits

    limits = ResourceLimits(cpu_seconds=3, memory_bytes=64 * 1024 * 1024, scratch_bytes=1_000)
    before = {
        which: resource.getrlimit(which)
        for which in (resource.RLIMIT_CPU, resource.RLIMIT_AS, resource.RLIMIT_FSIZE)
    }
    pid = os.fork()
    if pid == 0:  # pragma: no cover — the child never returns to the test runner
        try:
            apply_limits(limits)
            cpu_soft, _ = resource.getrlimit(resource.RLIMIT_CPU)
            as_soft, _ = resource.getrlimit(resource.RLIMIT_AS)
            core_soft, core_hard = resource.getrlimit(resource.RLIMIT_CORE)
            ok = (
                cpu_soft >= limits.cpu_seconds + SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS
                and as_soft > limits.memory_bytes * (SANDBOX_KERNEL_BACKSTOP_FACTOR - 1)
                and core_soft == 0
                and core_hard == 0
            )
        except Exception:  # noqa: BLE001 — the child reports through its exit status
            ok = False
        os._exit(0 if ok else 1)

    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

    # The parent's own limits are untouched: rlimits bind the child alone.
    for which, value in before.items():
        assert resource.getrlimit(which) == value


def test_a_loopback_proxy_and_a_usable_namespace_produce_kernel_enforced_egress() -> None:
    plan = plan_egress(
        EgressPolicy(proxy_url=LOOPBACK_PROXY, hosts=("api.datadoghq.com",)),
        namespace_available=True,
    )
    assert plan.isolate_network_namespace
    assert plan.strength is GuaranteeStrength.ENFORCED
    assert plan.permits("api.datadoghq.com")
    assert not plan.permits("attacker.example")


def test_a_remote_proxy_never_gets_the_namespace_however_capable_the_host() -> None:
    """A namespace with only ``lo`` cannot reach a proxy that is anywhere else.

    Choosing "stronger" over "works" here would produce a sandbox that cannot
    authenticate, which is how an isolation layer gets turned off.
    """
    plan = plan_egress(EgressPolicy(proxy_url=REMOTE_PROXY), namespace_available=True)
    assert not plan.isolate_network_namespace
    assert plan.strength is GuaranteeStrength.BEST_EFFORT


def test_the_plan_routes_every_scheme_through_the_proxy_and_exempts_only_it() -> None:
    policy = EgressPolicy(proxy_url=LOOPBACK_PROXY, hosts=("api.datadoghq.com",))
    plan = plan_egress(policy, namespace_available=False)

    assert plan.environment[SANDBOX_HTTP_PROXY_ENV] == LOOPBACK_PROXY
    assert plan.environment[SANDBOX_HTTPS_PROXY_ENV] == LOOPBACK_PROXY
    # Only the proxy itself is exempt from being proxied. An allow-listed vendor
    # still goes through, which is what makes the proxy's own list the second
    # enforcement point rather than a duplicate of this one.
    assert plan.environment[SANDBOX_NO_PROXY_ENV] == "127.0.0.1"
    assert "api.datadoghq.com" not in plan.environment[SANDBOX_NO_PROXY_ENV]


def test_the_namespace_probe_answers_without_raising() -> None:
    """Whatever this host allows, the probe returns a boolean rather than failing."""
    from platform.sandbox.profiles.process.network import network_namespace_available

    assert isinstance(network_namespace_available(), bool)
