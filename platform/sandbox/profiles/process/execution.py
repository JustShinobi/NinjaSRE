"""Spawning, watching, streaming, and killing — the part every profile shares.

This is the ``process`` profile's engine, and it is also what the container and
Kubernetes profiles' *local* engines drive. That is deliberate: streaming
semantics, the terminal-event contract, which limit reports which kind, and how
interruption races with completion are behaviours the contract suite asserts on
all three, so they are implemented once. A profile differs in where the process
runs and what confines it, not in what a caller observes.

Three details are load-bearing.

**Output is yielded as it arrives, and also accumulated.** A limit kill has to
carry the partial output — a truncated traceback is usually the whole diagnosis
— and a caller consuming the stream has already seen those bytes. The
accumulation is capped at a tail, because the failure mode here is a capability
that printed a gigabyte before it was killed.

**The watchdog kills the process group, not the process.** A capability that
forked and exited leaves children holding the pipes, and killing only the leader
produces a stream that never ends. ``start_new_session`` is what makes the group
exist to be killed.

**Termination is polite then absolute.** ``SIGTERM``, a short grace period, then
``SIGKILL``. The grace exists so an interpreter can run its exception handlers
and flush; it is not long enough to be worth trying to outlast.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from config.constants.security import (
    SANDBOX_MONITOR_INTERVAL_SECONDS,
    SANDBOX_TERMINATION_GRACE_SECONDS,
)
from platform.sandbox.errors import SandboxInterrupted, SandboxLimitExceeded
from platform.sandbox.port import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionResult,
    OutputChunk,
    OutputStream,
)
from platform.sandbox.profiles.process import limits_posix, limits_windows
from platform.sandbox.profiles.process.monitor import ResourceMonitor
from platform.sandbox.spec import LimitKind, ResourceLimits

#: How much of each stream rides along on a limit or interruption error. Enough
#: for a Python traceback and the lines around it; not enough to be a way of
#: getting a gigabyte of output into an exception message.
_ERROR_OUTPUT_TAIL_BYTES = 64 * 1024

#: How much is read from a pipe at once. Large enough that a chatty capability
#: does not produce a chunk per line, small enough that a caller sees progress.
_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Everything needed to start one command under one sandbox's constraints."""

    command: tuple[str, ...]
    cwd: Path
    scratch: Path
    environment: Mapping[str, str]
    limits: ResourceLimits
    stdin: bytes = b""
    isolate_network_namespace: bool = False


@dataclass
class RunningExecution:
    """One in-flight command, and the flag that cancels it.

    Mutable and deliberately not shared outside the runner that owns it. The
    interrupt path sets ``cancelled`` and signals; the streaming loop is what
    turns that into a ``SandboxInterrupted``, so there is exactly one place that
    decides how a cancelled execution ends.
    """

    process: asyncio.subprocess.Process
    cancelled: bool = False
    job: object | None = None
    limit_hit: LimitKind | None = None
    _terminating: bool = field(default=False, repr=False)

    async def cancel(self) -> None:
        """Ask this execution to stop, politely then absolutely. Idempotent."""
        self.cancelled = True
        await terminate(self)


async def terminate(execution: RunningExecution) -> None:
    """Stop ``execution``'s whole process group. Safe to call more than once."""
    if execution._terminating:
        return
    execution._terminating = True

    if execution.job is not None:
        limits_windows.terminate(execution.job)
        execution.job = None

    process = execution.process
    if process.returncode is not None:
        return

    _signal_group(process, signal.SIGTERM)
    with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=SANDBOX_TERMINATION_GRACE_SECONDS)
    if process.returncode is None:
        _signal_group(process, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            await process.wait()


def _signal_group(process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    """Send ``sig`` to the process group led by ``process``, or to it alone.

    Windows has no process groups in the POSIX sense and ``killpg`` does not
    exist there; the Job Object is what covers the descendants instead, and it
    has already been terminated by the time this runs.
    """
    try:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(os.getpgid(process.pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        with contextlib.suppress(ProcessLookupError):
            process.kill()


async def spawn(plan: LaunchPlan) -> RunningExecution:
    """Start ``plan``'s command in its own session, confined by its limits."""
    environment = dict(plan.environment)

    if sys.platform == "win32":
        process = await asyncio.create_subprocess_exec(
            *plan.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(plan.cwd),
            env=environment,
            creationflags=_windows_creation_flags(),
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *plan.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(plan.cwd),
            env=environment,
            preexec_fn=limits_posix.preexec(
                plan.limits,
                scratch=plan.cwd,
                isolate_network=plan.isolate_network_namespace,
            ),
        )

    job = None
    if sys.platform == "win32":
        job = limits_windows.create_job(plan.limits)
        limits_windows.assign(job, process.pid)

    execution = RunningExecution(process=process, job=job)
    if plan.stdin and process.stdin is not None:
        process.stdin.write(plan.stdin)
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await process.stdin.drain()
    if process.stdin is not None:
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            process.stdin.close()
    return execution


def _windows_creation_flags() -> int:
    """Return the flags that give the child its own console process group."""
    if sys.platform != "win32":
        return 0

    import subprocess  # noqa: PLC0415 — only the constant, and only on Windows

    return int(subprocess.CREATE_NEW_PROCESS_GROUP)


async def stream_execution(
    plan: LaunchPlan,
    *,
    sandbox_id: str,
    monitor: ResourceMonitor,
    wall_clock_seconds: float,
    register: object = None,
) -> AsyncIterator[ExecutionEvent]:
    """Run ``plan``, yielding output as it arrives and one completion at the end.

    Raises ``SandboxLimitExceeded`` naming the bound that stopped it, or
    ``SandboxInterrupted`` when something cancelled it from outside. Both carry
    the output produced so far, because a capability that was killed still
    learned something and throwing that away is how an investigation repeats
    work it already did.
    """
    started = time.monotonic()
    execution = await spawn(plan)
    if callable(register):
        register(execution)

    queue: asyncio.Queue[tuple[OutputStream, bytes] | None] = asyncio.Queue()
    readers = [
        asyncio.create_task(_pump(execution.process.stdout, OutputStream.STDOUT, queue)),
        asyncio.create_task(_pump(execution.process.stderr, OutputStream.STDERR, queue)),
    ]
    watchdog = asyncio.create_task(
        _watch(
            execution,
            plan=plan,
            monitor=monitor,
            wall_clock_seconds=wall_clock_seconds,
            started=started,
        )
    )

    stdout_tail = bytearray()
    stderr_tail = bytearray()
    open_streams = len(readers)

    try:
        while open_streams:
            item = await queue.get()
            if item is None:
                open_streams -= 1
                continue
            stream, data = item
            tail = stdout_tail if stream is OutputStream.STDOUT else stderr_tail
            tail.extend(data)
            del tail[:-_ERROR_OUTPUT_TAIL_BYTES]
            yield OutputChunk(stream=stream, data=data)

        await execution.process.wait()
    finally:
        watchdog.cancel()
        for reader in readers:
            reader.cancel()
        await asyncio.gather(watchdog, *readers, return_exceptions=True)

    duration = time.monotonic() - started

    if execution.limit_hit is not None:
        raise SandboxLimitExceeded(
            execution.limit_hit,
            sandbox_id=sandbox_id,
            allowed=plan.limits.value_of(execution.limit_hit)
            if execution.limit_hit is not LimitKind.WALL_CLOCK_SECONDS
            else wall_clock_seconds,
            stdout=bytes(stdout_tail),
            stderr=bytes(stderr_tail),
        )
    if execution.cancelled:
        raise SandboxInterrupted(sandbox_id)

    yield ExecutionCompleted(
        result=ExecutionResult(
            exit_code=execution.process.returncode or 0,
            duration_seconds=duration,
        )
    )


async def _pump(
    reader: asyncio.StreamReader | None,
    stream: OutputStream,
    queue: asyncio.Queue[tuple[OutputStream, bytes] | None],
) -> None:
    """Move one pipe's bytes into ``queue``, then post the end-of-stream marker."""
    if reader is None:
        await queue.put(None)
        return
    try:
        while True:
            data = await reader.read(_READ_CHUNK_BYTES)
            if not data:
                break
            await queue.put((stream, data))
    except (asyncio.CancelledError, ValueError):
        raise
    finally:
        await queue.put(None)


async def _watch(
    execution: RunningExecution,
    *,
    plan: LaunchPlan,
    monitor: ResourceMonitor,
    wall_clock_seconds: float,
    started: float,
) -> None:
    """Sample usage until a bound is crossed, then stop the process group.

    Records which bound it was on the execution before terminating, so the
    streaming loop reports a reason rather than an exit status. The sampler is
    the *explanation*; the operating system's own limits are the enforcement,
    and a bound crossed between two samples is still stopped by the kernel.
    """
    while execution.process.returncode is None:
        await asyncio.sleep(SANDBOX_MONITOR_INTERVAL_SECONDS)

        if time.monotonic() - started > wall_clock_seconds:
            execution.limit_hit = LimitKind.WALL_CLOCK_SECONDS
            await terminate(execution)
            return

        sample = monitor.sample(pid=execution.process.pid, scratch=plan.scratch)
        crossed = sample.exceeded(plan.limits)
        if crossed is not None:
            execution.limit_hit = crossed
            await terminate(execution)
            return


__all__ = [
    "LaunchPlan",
    "RunningExecution",
    "spawn",
    "stream_execution",
    "terminate",
]
