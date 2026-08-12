"""Reaching a node over SSH without ever building a command line.

The executor hands the transport a vector. The whole guarantee of that vector
survives only if the transport keeps it one: the moment it is joined into a
string for `ssh node "..."`, the remote shell parses it, and every check the
allowlist made becomes advisory.

OpenSSH passes multiple arguments to the remote end by joining them with spaces
and handing the result to the login shell. So the transport quotes each element
itself, once, before OpenSSH ever sees it — and that quoting is the thing under
test, because it is the one place where a value could still become syntax.
"""

from __future__ import annotations

import pytest

from gateway.executor.openssh import OpenSshRunner, remote_command

pytestmark = pytest.mark.unit


def test_each_element_is_quoted_so_the_remote_shell_cannot_read_it_as_syntax() -> None:
    # The allowlist would have refused this long before here. The transport is
    # the second line, and a second line that assumes the first held is not one.
    assert remote_command(["systemctl", "restart", "a b; rm -rf /"]) == (
        "systemctl restart 'a b; rm -rf /'"
    )


def test_an_ordinary_vector_is_not_mangled() -> None:
    assert remote_command(["pvecm", "status"]) == "pvecm status"


def test_a_single_quote_in_a_value_cannot_close_the_quoting() -> None:
    """The classic escape. If it closes, everything after it is syntax."""
    quoted = remote_command(["echo", "it's"])

    assert "'\"'\"'" in quoted or quoted.count("'") >= 4


def test_the_ssh_invocation_names_the_node_and_forbids_a_password_prompt() -> None:
    """A prompt would hang the executor until its timeout on any node whose key
    is wrong, which is a node outage that is really a configuration mistake."""
    argv = OpenSshRunner(user="ninjasre", identity="/etc/ninjasre/id_ed25519").ssh_argv(
        node="pve01", argv=["pvecm", "status"]
    )

    assert argv[0] == "ssh"
    assert "ninjasre@pve01" in argv
    assert "BatchMode=yes" in " ".join(argv)
    assert "/etc/ninjasre/id_ed25519" in argv
    assert argv[-1] == "pvecm status"


def test_host_key_checking_is_not_switched_off() -> None:
    """Turning it off would make the executor reachable by anything that can
    answer on the node's address, which is the whole attack this key protects."""
    argv = OpenSshRunner(user="ninjasre", identity="/k").ssh_argv(node="pve01", argv=["ls"])

    assert "StrictHostKeyChecking=no" not in " ".join(argv)


async def test_a_command_that_outlives_its_timeout_is_reported_rather_than_awaited() -> None:
    """A hung node must become a finding, not a request that never returns.

    The spawn is injected rather than the ssh binary swapped, so what runs here
    is the same code path a deployment runs — only the process it starts differs.
    """
    import asyncio

    async def _slow(*_argv: str, **_options: object) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "sleep", "30", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

    runner = OpenSshRunner(user="ninjasre", identity="/k", spawn=_slow)

    with pytest.raises(TimeoutError):
        await runner.run(node="pve01", argv=["pvecm", "status"], timeout_seconds=0.2)


async def test_what_the_transport_spawns_is_the_vector_it_built() -> None:
    """The spawn port must not become a place where the vector is rebuilt."""
    import asyncio

    seen: list[tuple[str, ...]] = []

    async def _record(*argv: str, **_options: object) -> asyncio.subprocess.Process:
        seen.append(argv)
        return await asyncio.create_subprocess_exec(
            "true", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

    runner = OpenSshRunner(user="ninjasre", identity="/k", spawn=_record)
    await runner.run(node="pve01", argv=["pvecm", "status"], timeout_seconds=5)

    assert list(seen[0]) == runner.ssh_argv(node="pve01", argv=["pvecm", "status"])
