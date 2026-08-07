"""One invocation: what it can render, what it talks to, and how it ends.

Every command body is the same four steps — read the invocation, call the
client, build the payload, emit it — and this module owns three of them so a
command owns only the middle one. That is what keeps ``--json``, the exit-code
contract, and Ctrl+C from being reimplemented eleven times with eleven small
differences.

The client is resolved lazily. ``ninjasre runs list --help`` must not need a
deployment, and an operator who mistyped a flag should be told that rather than
told the database is unreachable.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from typing import IO, Any, TypeVar

from config.constants.surfaces import (
    EXIT_INTERRUPTED,
    EXIT_OK,
)
from platform.observability.logging import get_logger
from surfaces.cli.client import Endpoint, LocalServices, PlatformClient, select_client
from surfaces.cli.errors import CliError
from surfaces.cli.output.degradation import Terminal, detect
from surfaces.cli.output.json_ import envelope_of, failure, render

logger = get_logger(__name__)

_Result = TypeVar("_Result")

#: Builds the in-process platform when there is one. Held as a callable rather
#: than a value because composing a deployment is expensive and most
#: invocations — ``--help``, ``--version``, anything against a remote endpoint —
#: never need one.
ServicesFactory = Callable[[], LocalServices]


@dataclass(slots=True)
class Invocation:
    """Everything one run of the CLI decided before a command body started."""

    terminal: Terminal = field(default_factory=lambda: detect(stream=sys.stdout))
    as_json: bool = False
    team_node_id: str = ""
    endpoint: Endpoint | None = None
    services_factory: ServicesFactory | None = None
    out: IO[str] = field(default_factory=lambda: sys.stdout)
    err: IO[str] = field(default_factory=lambda: sys.stderr)
    _client: PlatformClient | None = field(default=None, repr=False)

    def client(self) -> PlatformClient:
        """Return the deployment this invocation talks to, resolving it once.

        Raises:
            CliError: there is neither a local composition nor an endpoint.
        """
        if self._client is None:
            services = self.services_factory() if self.services_factory is not None else None
            self._client = select_client(services=services, endpoint=self.endpoint)
        return self._client

    def with_client(self, client: PlatformClient) -> Invocation:
        """Return this invocation bound to ``client``.

        What a test uses, and what the REPL uses to hand its own already-open
        client to a command rather than opening a second one.
        """
        self._client = client
        return self

    def write(self, text: str) -> None:
        """Write one block of output, newline-terminated."""
        if text:
            self.out.write(text if text.endswith("\n") else text + "\n")

    def write_error(self, text: str) -> None:
        """Write one block to the error stream, newline-terminated.

        Errors go to stderr even under ``--json``, so a script redirecting
        stdout into a parser gets a parseable document and a human watching the
        terminal still sees what went wrong.
        """
        if text:
            self.err.write(text if text.endswith("\n") else text + "\n")


@dataclass(frozen=True, slots=True)
class Output:
    """What one command produced, in both renderings.

    Two renderings of one value, built together, so the table and the JSON
    document cannot disagree about what happened.
    """

    command: str
    data: Mapping[str, Any] = field(default_factory=dict)
    text: str = ""
    warnings: tuple[str, ...] = ()
    code: int = EXIT_OK


def emit(invocation: Invocation, output: Output) -> int:
    """Render ``output`` the way this invocation was asked to, and return its code."""
    if invocation.as_json:
        invocation.write(render(envelope_of(output.command, output.data, warnings=output.warnings)))
    else:
        invocation.write(output.text)
        for warning in output.warnings:
            invocation.write_error(f"{invocation.terminal.glyph('warning')} {warning}")
    return output.code


def report_failure(invocation: Invocation, command: str, error: CliError) -> int:
    """Render ``error`` and return the code the process should exit with."""
    logger.info("cli.command_failed", command=command, code=error.code, error=error.message)
    if invocation.as_json:
        invocation.write(render(failure(command, str(error))))
    else:
        invocation.write_error(f"{invocation.terminal.glyph('failed')} {error}")
    return error.code


def run_command(
    invocation: Invocation,
    command: str,
    body: Callable[[], Coroutine[Any, Any, Output]],
    *,
    on_interrupt: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> int:
    """Run one command body and return the process exit code.

    Named ``run_command`` rather than ``execute`` on purpose: the storage
    boundary check rejects an ``execute(...)`` call outside
    ``platform/persistence/``, and a surface that shared the name with a
    database cursor would either trip that check or weaken it.

    The whole of the CLI's failure contract in one place: a ``CliError``
    becomes its own code, an interrupt becomes 130 after whatever cleanup the
    command declared, and anything else is allowed to propagate — an unexpected
    exception is a defect, and swallowing it into exit 1 is how a defect
    becomes a support ticket about "it just doesn't work".
    """
    try:
        return emit(invocation, asyncio.run(body()))
    except CliError as error:
        return report_failure(invocation, command, error)
    except KeyboardInterrupt:
        # The operator asked for it. The cleanup runs on its own loop because
        # the one the body was on is already unwinding.
        if on_interrupt is not None:
            asyncio.run(on_interrupt())
        invocation.write_error("interrupted")
        logger.info("cli.interrupted", command=command)
        return EXIT_INTERRUPTED


__all__ = [
    "Invocation",
    "Output",
    "ServicesFactory",
    "emit",
    "run_command",
    "report_failure",
]
