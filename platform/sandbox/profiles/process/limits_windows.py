"""Job Objects, and the one bound Windows will not give us.

A Job Object is the closest Windows equivalent of a cgroup: a kernel object a
process is assigned to, whose limits every descendant inherits and cannot
escape. ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` is the part that matters most —
when the handle closes, every process in the job dies, which makes release and
interruption exact rather than a best-effort walk of a process tree.

Three of the five bounds map cleanly:

- **memory** — ``ProcessMemoryLimit`` and ``JobMemoryLimit``, enforced by the
  kernel refusing the commit, exactly as ``RLIMIT_AS`` does.
- **process count** — ``ActiveProcessLimit``, which refuses the create rather
  than killing afterwards.
- **wall clock** — the same watchdog every platform uses.

**CPU time has no equivalent.** ``JOB_OBJECT_LIMIT_JOB_TIME`` bounds the job's
total *user-mode* time and reports it by terminating the job, but Windows offers
no per-process CPU accounting through this interface that the sampler can read,
so the runner cannot say "CPU budget" as the reason. The bound is set; the
explanation is not available. ``selection.py`` reports that at start,
and ``process`` on Windows is documented as a development profile.

Everything here is inert on any other platform: the module imports, and every
function returns without doing anything. That is deliberate — a Windows-only
module that could not be imported on Linux would be a module nobody could type
check on the machine they develop on.
"""

from __future__ import annotations

import sys
from typing import Any

from platform.sandbox.spec import ResourceLimits

WINDOWS_JOB_OBJECTS_AVAILABLE = sys.platform == "win32"

#: ``JOBOBJECTINFOCLASS.ExtendedLimitInformation``.
_EXTENDED_LIMIT_INFORMATION = 9

#: ``JOB_OBJECT_LIMIT_*`` flags, from ``winnt.h``.
_LIMIT_PROCESS_MEMORY = 0x0000_0100
_LIMIT_JOB_MEMORY = 0x0000_0200
_LIMIT_ACTIVE_PROCESS = 0x0000_0008
_LIMIT_KILL_ON_JOB_CLOSE = 0x0000_2000


def create_job(limits: ResourceLimits) -> Any:
    """Return a Job Object handle carrying ``limits``, or ``None`` off Windows.

    The handle is the resource. Closing it kills every process in the job, so
    the caller owns it for exactly as long as the sandbox exists — which is what
    makes "release the sandbox" and "nothing it started is still running" the
    same statement.
    """
    if sys.platform != "win32":
        return None

    import ctypes  # noqa: PLC0415 — Windows-only path
    import ctypes.wintypes  # noqa: PLC0415

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("LimitFlags", ctypes.wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.wintypes.DWORD),
            ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
            ("PriorityClass", ctypes.wintypes.DWORD),
            ("SchedulingClass", ctypes.wintypes.DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")

    information = _ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = (
        _LIMIT_PROCESS_MEMORY | _LIMIT_JOB_MEMORY | _LIMIT_ACTIVE_PROCESS | _LIMIT_KILL_ON_JOB_CLOSE
    )
    information.BasicLimitInformation.ActiveProcessLimit = limits.max_processes
    information.ProcessMemoryLimit = limits.memory_bytes
    information.JobMemoryLimit = limits.memory_bytes

    if not kernel32.SetInformationJobObject(
        handle,
        _EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise OSError(error, "SetInformationJobObject failed")
    return handle


def assign(job: Any, pid: int) -> None:
    """Put the process ``pid`` and everything it forks into ``job``.

    A no-op off Windows and for a ``None`` handle, so the runner does not branch
    on platform at the call site.
    """
    if sys.platform != "win32" or job is None:
        return

    import ctypes  # noqa: PLC0415 — Windows-only path

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel32.OpenProcess(0x0010 | 0x0200 | 0x1000, False, pid)
    if not process:
        raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
    try:
        if not kernel32.AssignProcessToJobObject(job, process):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
    finally:
        kernel32.CloseHandle(process)


def terminate(job: Any) -> None:
    """Kill everything in ``job`` and release the handle. Idempotent."""
    if sys.platform != "win32" or job is None:
        return

    import ctypes  # noqa: PLC0415 — Windows-only path

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject(job, 1)
    kernel32.CloseHandle(job)


__all__ = [
    "WINDOWS_JOB_OBJECTS_AVAILABLE",
    "assign",
    "create_job",
    "terminate",
]
