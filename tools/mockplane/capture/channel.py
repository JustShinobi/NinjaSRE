"""The read-only channel to the cluster, and the only way a command reaches one.

Every read goes through :meth:`ReadOnlyChannel.read`, which checks the allowlist
before anything is sent. There is deliberately no second method that skips the
check — the ad-hoc query tool is the same call with one command rather than
many, which is what makes "an ad-hoc query obeys the allowlist" a property of
the code rather than a promise in a document.

Connection details come from configuration at run time. The SSH identity is
supplied by the operator's own agent or key file and is never named here: this
is a development capture run by a human, and Article IV's rule that no
credential reaches the agent is not weakened by it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.fixtures import (
    NINJASRE_CAPTURE_NODES_ENV,
    NINJASRE_CAPTURE_SSH_USER_ENV,
)
from tools.mockplane.allowlist import Allowlist, CommandRefused

#: How long one read may take before the capture gives up on it. A capture that
#: hangs on a node with a wedged mount is a capture nobody finishes.
READ_TIMEOUT_SECONDS: Final = 30.0


class ChannelError(RuntimeError):
    """A read could not be made, or came back as something other than an answer."""


class NoConnectionDetails(RuntimeError):
    """Nothing in the configuration says which nodes to read."""


@runtime_checkable
class CommandRunner(Protocol):
    """Whatever carries one already-approved command to one node.

    A protocol rather than a concrete SSH call, for the reason every seam in
    this repository is a protocol: the parsers and the projection are then
    testable against recorded output, and the only thing that needs a cluster is
    the twenty lines that open a connection.
    """

    def run(self, node: str, command: str) -> str:
        """Return what ``command`` printed on ``node``."""


@dataclass(frozen=True, slots=True)
class NodeConfiguration:
    """Which nodes to read, and as whom.

    Read from the environment rather than written down, because the topology of
    somebody's infrastructure is theirs and does not belong in a repository.
    """

    #: Node name to address. The name is what records are attributed to; the
    #: address is what is connected to.
    hosts: Mapping[str, str]
    user: str = "root"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> NodeConfiguration:
        """Return the configured nodes.

        Raises:
            NoConnectionDetails: nothing names any node.
        """
        source = dict(environ if environ is not None else os.environ)
        raw = source.get(NINJASRE_CAPTURE_NODES_ENV, "").strip()
        if not raw:
            raise NoConnectionDetails(
                f"set {NINJASRE_CAPTURE_NODES_ENV} to a comma-separated list of "
                f"name=address pairs naming the nodes to read"
            )
        hosts: dict[str, str] = {}
        for pair in raw.split(","):
            name, separator, address = pair.partition("=")
            if not separator or not name.strip() or not address.strip():
                raise NoConnectionDetails(f"{pair!r} is not a name=address pair")
            hosts[name.strip()] = address.strip()
        return cls(
            hosts=hosts, user=source.get(NINJASRE_CAPTURE_SSH_USER_ENV, "").strip() or "root"
        )


@dataclass(frozen=True, slots=True)
class SshCommandRunner:
    """The shipped runner: one ``ssh`` invocation per read, no shell in between.

    ``ssh`` is given an argument vector rather than a command line, and the
    allowlist has already refused anything carrying a character that could end
    one command and start another. Both, because either alone is one mistake
    away from being the whole defence.
    """

    configuration: NodeConfiguration
    timeout_seconds: float = READ_TIMEOUT_SECONDS

    def run(self, node: str, command: str) -> str:
        """Return what ``command`` printed on ``node``.

        Raises:
            ChannelError: the node is not configured, the connection failed, or
                the command exited non-zero.
        """
        address = self.configuration.hosts.get(node)
        if address is None:
            raise ChannelError(f"{node!r} is not one of the configured nodes")
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            f"{self.configuration.user}@{address}",
            "--",
            *shlex.split(command),
        ]
        try:
            finished = subprocess.run(  # noqa: S603 — the vector is allowlisted, never a shell
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as failure:
            # The failure is named by its type rather than repeated. Both
            # ``OSError`` and ``TimeoutExpired`` render the whole argument
            # vector, and the argument vector holds the address — which would
            # put it in a log line before anonymisation had run.
            raise ChannelError(
                f"{node}: {command!r} could not be run ({type(failure).__name__})"
            ) from failure
        if finished.returncode != 0:
            # The node's stderr is not repeated here either, and for the same
            # reason: it routinely carries hostnames and paths.
            raise ChannelError(f"{node}: {command!r} exited {finished.returncode}")
        return finished.stdout


@dataclass(frozen=True, slots=True)
class RecordedCommandRunner:
    """A runner that answers from recorded output and refuses anything else.

    What the parser and projection suites drive. A read nobody recorded fails
    loudly rather than returning an empty string, because a parser proved
    against an empty string is a parser proved against nothing.
    """

    answers: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def run(self, node: str, command: str) -> str:
        """Return the recorded output of ``command`` on ``node``."""
        try:
            return self.answers[(node, command)]
        except KeyError:
            raise ChannelError(f"{node}: nothing was recorded for {command!r}") from None


@dataclass(frozen=True, slots=True)
class ReadOnlyChannel:
    """The one way a command reaches a node."""

    runner: CommandRunner
    allowlist: Allowlist

    def read(self, node: str, command: str) -> str:
        """Return what ``command`` printed on ``node``.

        Raises:
            CommandRefused: the allowlist does not declare it. Nothing is sent.
            ChannelError: the read failed.
        """
        self.allowlist.check(command)
        return self.runner.run(node, command)

    def read_json(self, node: str, command: str) -> Any:
        """Return the JSON ``command`` printed on ``node``.

        Raises:
            ChannelError: the output is not JSON, which for a ``pvesh`` read
                means the command answered an error rather than a payload.
        """
        raw = self.read(node, command)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise ChannelError(f"{node}: {command!r} did not answer JSON: {error}") from error

    def refuses(self, command: str) -> CommandRefused | None:
        """Return why ``command`` would be refused, or ``None`` if it would run.

        For the ad-hoc tool, which reports the refusal rather than raising it at
        somebody typing at a terminal.
        """
        try:
            self.allowlist.check(command)
        except CommandRefused as refusal:
            return refusal
        return None


__all__ = [
    "READ_TIMEOUT_SECONDS",
    "ChannelError",
    "CommandRunner",
    "NoConnectionDetails",
    "NodeConfiguration",
    "ReadOnlyChannel",
    "RecordedCommandRunner",
    "SshCommandRunner",
]
