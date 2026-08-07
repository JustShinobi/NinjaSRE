"""Running an external command, as a port, so a suite can be driven without one.

Every piece of infrastructure these suites touch is reached through somebody
else's command-line tool — the cluster's, the package manager's, the cloud
provider's. Calling ``subprocess`` directly from each of them would make the
whole of the chaos and end-to-end trees untestable without the real thing
installed, which is precisely the position that leads to infrastructure code
nobody has ever run except in anger.

So there is one port. ``SubprocessRunner`` is what a live run uses;
``RecordedRunner`` answers from a script and remembers what it was asked, which
is what lets the setup, installation, provisioning, and teardown paths be
asserted on a machine with none of those tools present.

Nothing here reads or forwards a credential. The external tool authenticates
itself from the operator's own environment, which is the only arrangement in
which a suite that provisions cloud infrastructure does not become a place a
secret passes through.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

#: How long a command may run before it is abandoned. Generous, because these
#: wrap installations and cluster creation, and mean because a hung command in
#: CI is an hour of a runner nobody gets back.
DEFAULT_COMMAND_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What one external command did."""

    argv: tuple[str, ...]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the command reported success."""
        return self.returncode == 0

    @property
    def message(self) -> str:
        """Return the shortest useful description of a failure."""
        detail = (self.stderr or self.stdout).strip().splitlines()
        return detail[-1] if detail else f"exit status {self.returncode}"


class CommandFailed(RuntimeError):
    """An external command a suite depended on did not succeed."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        super().__init__(f"{' '.join(result.argv)}: {result.message}")


@runtime_checkable
class CommandRunner(Protocol):
    """Whatever runs an external command and reports what happened."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        stdin: str = "",
    ) -> CommandResult:
        """Return the outcome of running ``argv``, without raising on failure."""


@dataclass(frozen=True, slots=True)
class SubprocessRunner:
    """Runs the command, for real.

    ``environment`` carries the non-secret settings a tool needs to find its
    target — a kubeconfig path, a cluster context, a region. It is a mapping the
    caller states rather than the ambient environment, so what a suite passes to
    a tool is visible in one place.
    """

    environment: Mapping[str, str] = field(default_factory=dict)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        stdin: str = "",
    ) -> CommandResult:
        """Return the outcome of running ``argv``, without raising on failure."""
        import os

        arguments = tuple(str(item) for item in argv)
        merged = {**os.environ, **self.environment}
        try:
            completed = subprocess.run(  # noqa: S603 - argv is a list, never a shell string
                arguments,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin or None,
                env=merged,
                check=False,
            )
        except FileNotFoundError:
            return CommandResult(
                argv=arguments, returncode=127, stderr=f"{arguments[0]}: not found"
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                argv=arguments,
                returncode=124,
                stderr=f"timed out after {timeout:g}s",
            )
        return CommandResult(
            argv=arguments,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


#: How a recorded runner decides what to answer: given the argv, return a result
#: or ``None`` to fall through to the next rule.
CommandRule = Callable[[tuple[str, ...]], CommandResult | None]


@dataclass(slots=True)
class RecordedRunner:
    """Answers from a script, and keeps every command it was asked to run.

    The commands are the assertion. "Did teardown actually ask for the cluster
    to be deleted" is a question about what was invoked, and the alternative —
    asserting on the effect — needs the infrastructure this exists to do
    without.
    """

    rules: tuple[CommandRule, ...] = ()
    default: CommandResult | None = None
    invocations: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        stdin: str = "",
    ) -> CommandResult:
        """Return the scripted answer for ``argv``, recording the call."""
        arguments = tuple(str(item) for item in argv)
        self.invocations.append(arguments)
        for rule in self.rules:
            answer = rule(arguments)
            if answer is not None:
                return answer
        if self.default is not None:
            return CommandResult(
                argv=arguments,
                returncode=self.default.returncode,
                stdout=self.default.stdout,
                stderr=self.default.stderr,
            )
        return CommandResult(argv=arguments)

    def ran(self, *fragments: str) -> bool:
        """Return whether some invocation contained every fragment, in order."""
        for invocation in self.invocations:
            joined = " ".join(invocation)
            position = 0
            for fragment in fragments:
                found = joined.find(fragment, position)
                if found < 0:
                    break
                position = found + len(fragment)
            else:
                return True
        return False


def answering(*fragments: str, stdout: str = "", returncode: int = 0) -> CommandRule:
    """Return a rule answering any command containing every fragment."""

    def rule(argv: tuple[str, ...]) -> CommandResult | None:
        joined = " ".join(argv)
        if all(fragment in joined for fragment in fragments):
            return CommandResult(argv=argv, returncode=returncode, stdout=stdout)
        return None

    return rule


def executable_present(name: str) -> bool:
    """Return whether ``name`` is an executable this machine can run."""
    return shutil.which(name) is not None


__all__ = [
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "CommandFailed",
    "CommandResult",
    "CommandRule",
    "CommandRunner",
    "RecordedRunner",
    "SubprocessRunner",
    "answering",
    "executable_present",
]
