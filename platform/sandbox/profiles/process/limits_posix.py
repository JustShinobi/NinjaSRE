"""POSIX resource limits, applied in the child between fork and exec.

``resource.setrlimit`` in a ``preexec_fn`` is the one place these can be set:
after the fork so they bind the child alone, before the exec so the child cannot
raise its own soft limits back up. A limit applied by the parent would bind the
agent; a limit applied by the child after exec would be a limit the capability
chose to keep.

**Every rlimit here sits above the declared bound, not on it.** The sampler in
``monitor.py`` holds the declared value and kills with a reason; these are the
backstop for the spike it polls straight past. Setting both at the same number
would mean the kernel always won the race, every limit would arrive as a bare
signal, and "which bound was crossed" would be unanswerable.

- ``RLIMIT_CPU`` — consumed CPU seconds, a fixed margin above the budget. The
  kernel sends ``SIGXCPU`` at the soft limit and ``SIGKILL`` at the hard one, so
  even the backstop gives a well-behaved process a chance to flush.
- ``RLIMIT_AS`` — address space, well above the memory ceiling. Address space is
  not RSS and CPython reserves far more of the first than it uses of the second,
  which is why this has a floor as well as a factor.
- ``RLIMIT_FSIZE`` — the largest single file, above the scratch quota. It stops
  one write being the whole quota faster than a poll interval.
- ``RLIMIT_CORE`` — zero, and this one is exact. A core dump of a capability
  that just read customer data is a file of customer data outside the scratch
  mount, and there is no version of that which is acceptable.

``RLIMIT_NPROC`` is deliberately **not** set. It counts processes per *user*,
and a sandbox runs as the same user as the agent — so a per-sandbox value low
enough to be a bound would refuse the agent's own next fork, and a value high
enough to be safe would bound nothing. The process ceiling is held by counting
the sandbox's process group (``monitor.py``) on POSIX and by a Job Object's
``ActiveProcessLimit``, which *is* per-job, on Windows.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from config.constants.security import (
    SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS,
    SANDBOX_KERNEL_BACKSTOP_FACTOR,
    SANDBOX_MEMORY_BACKSTOP_FLOOR_BYTES,
)
from platform.sandbox.spec import ResourceLimits

#: How much slack the hard CPU limit gets over the soft one. One second, which
#: is long enough for a Python interpreter to run a ``SIGXCPU`` handler and
#: short enough that a process ignoring the signal is stopped promptly.
_CPU_HARD_MARGIN_SECONDS = 1

POSIX_LIMITS_AVAILABLE = sys.platform != "win32"


def apply_limits(limits: ResourceLimits) -> None:
    """Set this process's rlimits from ``limits``.

    Called in the child between fork and exec, so it must not allocate, log, or
    touch a lock. Failures are swallowed per limit rather than in aggregate: a
    host that refuses ``RLIMIT_NPROC`` should still get the memory ceiling, and
    raising here would fail the exec with an error the parent reads as "the
    command does not exist".
    """
    import resource  # noqa: PLC0415 — POSIX-only, imported where it is used

    cpu = limits.cpu_seconds + SANDBOX_CPU_BACKSTOP_MARGIN_SECONDS
    memory = max(
        limits.memory_bytes * SANDBOX_KERNEL_BACKSTOP_FACTOR,
        SANDBOX_MEMORY_BACKSTOP_FLOOR_BYTES,
    )

    _try_set(resource.RLIMIT_CPU, cpu, cpu + _CPU_HARD_MARGIN_SECONDS)
    _try_set(resource.RLIMIT_AS, memory, memory)
    if limits.scratch_bytes:
        scratch = limits.scratch_bytes * SANDBOX_KERNEL_BACKSTOP_FACTOR
        _try_set(resource.RLIMIT_FSIZE, scratch, scratch)
    _try_set(resource.RLIMIT_CORE, 0, 0)


def _try_set(which: int, soft: int, hard: int) -> None:
    """Set one rlimit, ignoring a host that will not allow it."""
    import resource  # noqa: PLC0415 — POSIX-only, imported where it is used

    try:
        current_soft, current_hard = resource.getrlimit(which)
        if current_hard != resource.RLIM_INFINITY:
            soft = min(soft, current_hard)
            hard = min(hard, current_hard)
        resource.setrlimit(which, (soft, hard))
    except (OSError, ValueError):
        return


def preexec(limits: ResourceLimits, *, scratch: Path, isolate_network: bool) -> Callable[[], None]:
    """Return the function the child runs between fork and exec.

    It does three things in order, and the order is load-bearing. The session is
    created first so that everything after it — including the exec'd command and
    anything it forks — is in one process group the runner can signal as a unit.
    Network isolation comes next, because it can fail and the failure has to
    stop the exec rather than let an unisolated command run. Limits come last,
    since a process that has already dropped below its own limits cannot always
    perform the earlier steps.
    """

    def _child() -> None:
        os.setsid()
        if isolate_network:
            _unshare_network()
        os.chdir(scratch)
        apply_limits(limits)

    return _child


def _unshare_network() -> None:
    """Put this process in a network namespace containing only loopback.

    Raises ``OSError`` if the kernel refuses, which is deliberate: the caller
    only asks for this when the probe said it would work, so a refusal here
    means the host changed underneath us and running unisolated would be the
    wrong recovery.
    """
    import ctypes  # noqa: PLC0415 — only reached on POSIX, and only when probed

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(CLONE_NEWUSER | CLONE_NEWNET) != 0:
        raise OSError(ctypes.get_errno(), "unshare(CLONE_NEWUSER|CLONE_NEWNET) refused")


#: From ``linux/sched.h``. Written out rather than read from a header because
#: there is no portable way to read one, and these two values have been stable
#: for the lifetime of the flags.
CLONE_NEWNET = 0x4000_0000
CLONE_NEWUSER = 0x1000_0000


__all__ = [
    "CLONE_NEWNET",
    "CLONE_NEWUSER",
    "POSIX_LIMITS_AVAILABLE",
    "apply_limits",
    "preexec",
]
