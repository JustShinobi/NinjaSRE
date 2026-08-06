"""One suite, three profiles: what a capability may assume wherever it runs.

Everything here runs once per row of ``conftest.py``'s ``profile`` fixture. That
is one suite in one file: identical behaviour is not a claim in a document,
it is a suite that fails when it stops being true.
"""

from __future__ import annotations

from collections.abc import Callable

import probes
import pytest

from platform.sandbox import (
    ContentBundle,
    ExecutionCompleted,
    ExecutionRequest,
    LimitKind,
    OutputChunk,
    OutputStream,
    ResourceLimits,
    Sandbox,
    SandboxExpired,
    SandboxInterrupted,
    SandboxLimitExceeded,
    SandboxNotFound,
    SandboxSpec,
)
from platform.sandbox.trace import CollectingSandboxEvents, SandboxEventKind

pytestmark = pytest.mark.contract


async def test_provision_returns_a_usable_instance_scoped_to_the_spec(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        assert instance.profile is sandbox.profile
        assert instance.org_id == spec.org_id
        assert instance.team_id == spec.team_id
        assert instance.investigation_id == spec.investigation_id
        assert instance.state.usable
        assert instance.belongs_to(spec)
        assert not instance.is_expired()
        assert instance.expires_at > instance.created_at
        assert instance.scratch_path
    finally:
        await sandbox.release(instance)


async def test_execute_returns_output_and_exit_status(sandbox: Sandbox, spec: SandboxSpec) -> None:
    instance = await sandbox.provision(spec)
    try:
        result = await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))
        assert result.succeeded
        assert result.stdout == b"out"
        assert result.stderr == b"err"
        assert result.duration_seconds >= 0.0
    finally:
        await sandbox.release(instance)


async def test_a_failing_command_is_a_status_not_an_exception(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        result = await sandbox.execute(instance, ExecutionRequest(command=probes.EXIT_THREE))
        assert not result.succeeded
        assert result.exit_code == 3
    finally:
        await sandbox.release(instance)


async def test_stream_yields_output_before_exactly_one_completion(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        events = [
            event
            async for event in sandbox.stream(instance, ExecutionRequest(command=probes.CHUNKED))
        ]
    finally:
        await sandbox.release(instance)

    completions = [event for event in events if isinstance(event, ExecutionCompleted)]
    assert len(completions) == 1
    assert isinstance(events[-1], ExecutionCompleted)

    chunks = [event for event in events if isinstance(event, OutputChunk)]
    assert chunks, "a streaming profile that emitted nothing is not streaming"
    assert all(chunk.stream is OutputStream.STDOUT for chunk in chunks)
    assert b"".join(chunk.data for chunk in chunks) == b"".join(
        f"chunk{index}\n".encode() for index in range(5)
    )


async def test_stream_and_execute_report_the_same_thing(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        buffered = await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))
        streamed = [
            event
            async for event in sandbox.stream(instance, ExecutionRequest(command=probes.HELLO))
        ]
    finally:
        await sandbox.release(instance)

    completion = streamed[-1]
    assert isinstance(completion, ExecutionCompleted)
    assert completion.result.exit_code == buffered.exit_code
    assert (
        b"".join(
            event.data
            for event in streamed
            if isinstance(event, OutputChunk) and event.stream is OutputStream.STDOUT
        )
        == buffered.stdout
    )


async def test_stdin_reaches_the_command(sandbox: Sandbox, spec: SandboxSpec) -> None:
    instance = await sandbox.provision(spec)
    try:
        result = await sandbox.execute(
            instance,
            ExecutionRequest(
                command=probes.python("import sys; sys.stdout.write(sys.stdin.read().upper())"),
                stdin=b"payload",
            ),
        )
    finally:
        await sandbox.release(instance)
    assert result.stdout == b"PAYLOAD"


async def test_the_environment_carries_the_proxy_and_nothing_inherited(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    """A sandbox's environment is built, never inherited (the secrets-never-reach-the-agent rule, defence in depth)."""
    instance = await sandbox.provision(spec)
    try:
        result = await sandbox.execute(
            instance,
            ExecutionRequest(
                command=probes.python(
                    "import os, sys; sys.stdout.write('\\n'.join(sorted(os.environ)))"
                )
            ),
        )
    finally:
        await sandbox.release(instance)

    names = set(result.stdout.decode().splitlines())
    assert "HTTPS_PROXY" in names
    assert "HTTP_PROXY" in names
    # Nothing from the agent's own environment survives into the sandbox. The
    # agent holds no credential either — this is the second wall, not the first.
    assert not {name for name in names if name.startswith(("NINJASRE_", "AWS_", "OPENAI_"))}


@pytest.mark.parametrize(
    ("limits", "command", "expected"),
    [
        pytest.param(
            ResourceLimits(wall_clock_seconds=1.0),
            probes.SLEEP_FOREVER,
            LimitKind.WALL_CLOCK_SECONDS,
            id="wall-clock",
        ),
        pytest.param(
            ResourceLimits(cpu_seconds=1, wall_clock_seconds=30.0),
            probes.BURN_CPU,
            LimitKind.CPU_SECONDS,
            id="cpu",
        ),
        pytest.param(
            ResourceLimits(memory_bytes=128 * 1024 * 1024, wall_clock_seconds=30.0),
            probes.allocate(400),
            LimitKind.MEMORY_BYTES,
            id="memory",
        ),
        pytest.param(
            ResourceLimits(scratch_bytes=2 * 1024 * 1024, wall_clock_seconds=30.0),
            probes.fill_scratch(8),
            LimitKind.SCRATCH_BYTES,
            id="scratch",
        ),
        pytest.param(
            ResourceLimits(max_processes=3, wall_clock_seconds=30.0),
            probes.fork_children(6),
            LimitKind.PROCESS_COUNT,
            id="processes",
        ),
    ],
)
async def test_crossing_a_bound_terminates_and_names_which_one(
    sandbox: Sandbox,
    make_spec: Callable[..., SandboxSpec],
    limits: ResourceLimits,
    command: tuple[str, ...],
    expected: LimitKind,
) -> None:
    """Every bound is enforced, and the error says which one stopped the work."""
    instance = await sandbox.provision(make_spec(limits=limits))
    try:
        with pytest.raises(SandboxLimitExceeded) as raised:
            await sandbox.execute(instance, ExecutionRequest(command=command))
    finally:
        await sandbox.release(instance)

    assert raised.value.limit is expected
    assert raised.value.sandbox_id == instance.sandbox_id
    assert str(expected.description) in str(raised.value)


async def test_a_request_timeout_narrows_the_wall_clock_bound_but_never_widens_it(
    sandbox: Sandbox, make_spec: Callable[..., SandboxSpec]
) -> None:
    instance = await sandbox.provision(make_spec(limits=ResourceLimits(wall_clock_seconds=60.0)))
    try:
        with pytest.raises(SandboxLimitExceeded) as raised:
            await sandbox.execute(
                instance, ExecutionRequest(command=probes.SLEEP_FOREVER, timeout_seconds=1.0)
            )
    finally:
        await sandbox.release(instance)
    assert raised.value.limit is LimitKind.WALL_CLOCK_SECONDS


async def test_interrupt_stops_a_running_execution(sandbox: Sandbox, spec: SandboxSpec) -> None:
    """Cancellation actually stops the work, rather than stopping waiting for it."""
    import asyncio

    instance = await sandbox.provision(spec)

    async def run() -> None:
        await sandbox.execute(instance, ExecutionRequest(command=probes.SLEEP_FOREVER))

    task = asyncio.create_task(run())
    await asyncio.sleep(0.3)
    try:
        await sandbox.interrupt(instance)
        with pytest.raises(SandboxInterrupted):
            await asyncio.wait_for(task, timeout=15)
    finally:
        await sandbox.release(instance)


async def test_interrupting_an_idle_sandbox_is_a_no_op(sandbox: Sandbox, spec: SandboxSpec) -> None:
    instance = await sandbox.provision(spec)
    try:
        await sandbox.interrupt(instance)
        result = await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))
    finally:
        await sandbox.release(instance)
    assert result.succeeded


async def test_release_is_idempotent_and_then_refuses_work(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    await sandbox.release(instance)
    await sandbox.release(instance)

    with pytest.raises(SandboxNotFound):
        await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))


async def test_an_expired_sandbox_refuses_to_execute(
    sandbox: Sandbox, make_spec: Callable[..., SandboxSpec]
) -> None:
    """A TTL bounds a sandbox's life whether or not anything reaped it yet.

    A real one-second TTL rather than a fabricated expiry on the handle. A caller
    holding a stale instance is not the case that matters — the runner is the
    source of truth for its own instances, so the assertion has to be against a
    sandbox that genuinely aged out.
    """
    import asyncio

    instance = await sandbox.provision(make_spec(ttl_seconds=1))
    try:
        await asyncio.sleep(1.1)
        with pytest.raises(SandboxExpired):
            await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))
    finally:
        await sandbox.release(instance)


async def test_the_ttl_can_be_refreshed_while_an_investigation_is_active(
    sandbox: Sandbox, make_spec: Callable[..., SandboxSpec]
) -> None:
    """The other half of a TTL: an investigation that is still working says so."""
    instance = await sandbox.provision(make_spec(ttl_seconds=2))
    try:
        refreshed = await sandbox.refresh(instance)
        assert refreshed.expires_at > instance.expires_at
        result = await sandbox.execute(refreshed, ExecutionRequest(command=probes.HELLO))
        assert result.succeeded
    finally:
        await sandbox.release(instance)


async def test_scratch_is_writable_and_is_where_a_command_starts(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        written = await sandbox.execute(
            instance, ExecutionRequest(command=probes.write_file("note.txt", "hello"))
        )
        assert written.succeeded
        read = await sandbox.execute(
            instance, ExecutionRequest(command=probes.read_file("note.txt"))
        )
    finally:
        await sandbox.release(instance)
    assert read.stdout == b"hello"


async def test_delivered_content_is_readable_and_cannot_be_rewritten(
    sandbox: Sandbox, make_spec: Callable[..., SandboxSpec]
) -> None:
    """A sandbox must not be able to modify what it will execute next."""
    bundle = ContentBundle.from_mapping({"skills/triage.md": "# triage\n"})
    instance = await sandbox.provision(make_spec(content=bundle))
    try:
        target = f"{instance.content_path}/skills/triage.md"
        read = await sandbox.execute(instance, ExecutionRequest(command=probes.read_file(target)))
        assert read.stdout == b"# triage\n"

        tampered = await sandbox.execute(
            instance, ExecutionRequest(command=probes.overwrite_content(target))
        )
        assert tampered.stdout.startswith(b"DENIED")
        assert instance.content_digest == bundle.digest
    finally:
        await sandbox.release(instance)


async def test_lifecycle_events_reach_the_trace(
    sandbox: Sandbox, spec: SandboxSpec, events: CollectingSandboxEvents
) -> None:
    """What the isolation layer did is recorded, not inferred afterwards."""
    instance = await sandbox.provision(spec)
    await sandbox.execute(instance, ExecutionRequest(command=probes.HELLO))
    await sandbox.release(instance)

    kinds = [event.kind for event in events.for_investigation(spec.investigation_id)]
    assert SandboxEventKind.PROVISIONED in kinds
    assert SandboxEventKind.EXECUTION_STARTED in kinds
    assert SandboxEventKind.EXECUTION_FINISHED in kinds
    assert SandboxEventKind.RELEASED in kinds
    assert kinds.index(SandboxEventKind.PROVISIONED) < kinds.index(SandboxEventKind.RELEASED)

    provisioned = events.of_kind(SandboxEventKind.PROVISIONED)[0]
    assert provisioned.duration_seconds is not None
    assert provisioned.org_id == spec.org_id
    assert provisioned.profile is sandbox.profile
