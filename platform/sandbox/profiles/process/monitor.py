"""Watching a running sandbox closely enough to say *why* it was killed.

The operating system already enforces the bounds. ``RLIMIT_AS`` refuses the
allocation, ``RLIMIT_CPU`` sends ``SIGXCPU``, a Job Object refuses the fork —
none of that is negotiable and none of it is what this module does.

What the operating system does *not* do is explain itself. An rlimit kill
arrives as a signal number, and "your capability died on signal 9" sends every
operator to the wrong place. What is needed is *which* bound was crossed, so the runner
samples usage while the process runs and, when a sample crosses a limit, kills
the process itself with the reason already known.

That makes the reason authoritative and the enforcement redundant, which is the
right way round: if the sampler misses a spike between two polls the kernel
still stops it, and the worst case is a kill whose reason is "the operating
system did it" rather than a bound that was not enforced.

Three readers, because there is no portable way to ask. Linux reads ``/proc``,
which is exact and costs two file reads. Other POSIX systems shell out to
``ps``, which is slower and is why the interval is what it is. Windows reads the
Job Object's own accounting, and has no CPU counter to read — that is the gap
``selection.py`` reports at start.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from platform.sandbox.spec import LimitKind, ResourceLimits


@dataclass(frozen=True, slots=True)
class ResourceSample:
    """One observation of what a sandbox is currently consuming.

    Every field but ``scratch_bytes`` is optional, and ``None`` means "this host
    cannot tell me", not "zero". Treating an unreadable counter as zero is how a
    bound silently stops being checked on the one platform where it mattered.
    """

    scratch_bytes: int = 0
    cpu_seconds: float | None = None
    memory_bytes: int | None = None
    process_count: int | None = None

    def exceeded(self, limits: ResourceLimits) -> LimitKind | None:
        """Return the first bound this sample crosses, or ``None``.

        Order matters only in that a sample crossing two bounds reports one, and
        reporting the memory ceiling before the CPU budget is the more useful
        answer: a capability that allocated a gigabyte in a loop is described by
        the allocation, not by the loop.
        """
        if self.memory_bytes is not None and self.memory_bytes > limits.memory_bytes:
            return LimitKind.MEMORY_BYTES
        if self.scratch_bytes > limits.scratch_bytes:
            return LimitKind.SCRATCH_BYTES
        if self.process_count is not None and self.process_count > limits.max_processes:
            return LimitKind.PROCESS_COUNT
        if self.cpu_seconds is not None and self.cpu_seconds > limits.cpu_seconds:
            return LimitKind.CPU_SECONDS
        return None


@runtime_checkable
class ResourceMonitor(Protocol):
    """Reads what one sandbox's process tree is consuming right now."""

    def sample(self, *, pid: int, scratch: Path) -> ResourceSample:
        """Return current usage for the process group led by ``pid``.

        Never raises for a process that has already exited: sampling races with
        termination by construction, and a monitor that threw on the race would
        turn every clean exit into an error on a busy machine.
        """


def directory_bytes(root: Path) -> int:
    """Return the total size of every file under ``root``.

    Walked rather than cached. A quota that trusted a running total would be
    wrong the first time a capability truncated a file, and the scratch mount is
    small by construction — that is the point of the bound.
    """
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            # The directory went away underneath us, which is what release
            # looks like from here. A partial total is the right answer.
            continue
    return total


class ProcResourceMonitor:
    """Reads Linux ``/proc``, which is exact and costs two small file reads."""

    __slots__ = ("_clock_ticks", "_page_size")

    def __init__(self) -> None:
        self._clock_ticks = os.sysconf("SC_CLK_TCK")
        self._page_size = os.sysconf("SC_PAGE_SIZE")

    def sample(self, *, pid: int, scratch: Path) -> ResourceSample:
        """Return usage summed over every process in ``pid``'s process group."""
        cpu_ticks = 0.0
        rss_pages = 0
        count = 0

        for entry in _proc_pids():
            stat = _read_proc_stat(entry)
            if stat is None:
                continue
            pgrp, utime, stime, rss = stat
            if pgrp != pid:
                continue
            count += 1
            cpu_ticks += utime + stime
            rss_pages += rss

        if count == 0:
            return ResourceSample(scratch_bytes=directory_bytes(scratch))
        return ResourceSample(
            scratch_bytes=directory_bytes(scratch),
            cpu_seconds=cpu_ticks / self._clock_ticks,
            memory_bytes=rss_pages * self._page_size,
            process_count=count,
        )


def _proc_pids() -> list[str]:
    """Return the numeric entries of ``/proc``, or nothing if it is unreadable."""
    try:
        return [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return []


def _read_proc_stat(pid: str) -> tuple[int, float, float, int] | None:
    """Return ``(pgrp, utime, stime, rss_pages)`` for ``pid``, or ``None``.

    The comm field can contain spaces and parentheses, so the line is split at
    the *last* ``)`` rather than tokenised — a process named ``(evil) 1 2 3``
    would otherwise shift every field after it.
    """
    try:
        line = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    close = line.rfind(")")
    if close < 0:
        return None
    fields = line[close + 2 :].split()
    if len(fields) < 22:
        return None
    try:
        # Offsets are relative to field 3 (state), which is what remains after
        # the comm field is cut: pgrp is field 5, utime 14, stime 15, rss 24.
        return (int(fields[2]), float(fields[11]), float(fields[12]), int(fields[21]))
    except ValueError:
        return None


class PsResourceMonitor:
    """Reads ``ps`` for the POSIX systems that are not Linux.

    One subprocess per sample, which is why the sampling interval is measured in
    tens of milliseconds rather than milliseconds. macOS has no ``/proc`` and
    exposing the ``libproc`` calls through ``ctypes`` would be a second
    platform-specific implementation to maintain for a development profile.
    """

    __slots__ = ()

    def sample(self, *, pid: int, scratch: Path) -> ResourceSample:
        """Return usage summed over the process group led by ``pid``."""
        scratch_bytes = directory_bytes(scratch)
        try:
            completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
                ["ps", "-o", "pgid=,rss=,time=", "-A"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ResourceSample(scratch_bytes=scratch_bytes)

        cpu_seconds = 0.0
        rss_kib = 0
        count = 0
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) < 3 or not fields[0].isdigit():
                continue
            if int(fields[0]) != pid:
                continue
            count += 1
            rss_kib += int(fields[1]) if fields[1].isdigit() else 0
            cpu_seconds += _parse_ps_time(fields[2])

        if count == 0:
            return ResourceSample(scratch_bytes=scratch_bytes)
        return ResourceSample(
            scratch_bytes=scratch_bytes,
            cpu_seconds=cpu_seconds,
            memory_bytes=rss_kib * 1024,
            process_count=count,
        )


def _parse_ps_time(value: str) -> float:
    """Return ``ps``'s ``[[dd-]hh:]mm:ss`` duration in seconds."""
    days = 0
    if "-" in value:
        head, _, value = value.partition("-")
        days = int(head) if head.isdigit() else 0
    parts = value.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds + days * 86_400


class ScratchOnlyMonitor:
    """Reports the scratch quota and nothing else.

    The Windows reader and the fallback for any host whose process accounting
    cannot be read. The bounds it cannot see are still enforced — by Job Object
    on Windows, by rlimits everywhere else — so this is a loss of *explanation*,
    which is what ``selection.py`` reports at start rather than hiding.
    """

    __slots__ = ()

    def sample(self, *, pid: int, scratch: Path) -> ResourceSample:
        """Return the scratch mount's current size."""
        return ResourceSample(scratch_bytes=directory_bytes(scratch))


def default_monitor(*, system: str | None = None) -> ResourceMonitor:
    """Return the reader that works on ``system``, defaulting to this host."""
    host = system if system is not None else sys.platform
    if host.startswith("linux"):
        return ProcResourceMonitor()
    if host == "win32":
        return ScratchOnlyMonitor()
    return PsResourceMonitor()


__all__ = [
    "ProcResourceMonitor",
    "PsResourceMonitor",
    "ResourceMonitor",
    "ResourceSample",
    "ScratchOnlyMonitor",
    "default_monitor",
    "directory_bytes",
]
