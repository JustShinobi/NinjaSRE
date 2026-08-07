"""The exit-code contract, and the one exception that carries it.

A CLI is scriptable when its failures are distinguishable. ``ninjasre
investigate || handle_it`` is a shell script somebody writes once and then
maintains for a year, and it is only correct if "the provider is unreachable"
and "you named a run that does not exist" are different numbers that stay
different.

So every failure the CLI reports raises a ``CliError`` carrying its code, the
codes are named constants in ``config/constants/``, and the mapping below is
the documentation — printed by ``ninjasre --exit-codes`` rather than living in
a document that drifts from the code.

Two rules hold this together, and both are asserted by the contract suite:

- **A code means one thing.** Reusing one for a second failure mode makes an
  operator's branch wrong in a way nothing announces.
- **2 is the framework's.** A usage error exits 2 before any command body runs,
  so nothing else may claim it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from config.constants.surfaces import (
    EXIT_CONFIGURATION,
    EXIT_DENIED,
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_NEEDS_APPROVAL,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    EXIT_USAGE,
)

#: What each code means, in the words the CLI prints. The single source: the
#: help text, the documentation, and the contract test all read this.
EXIT_CODE_MEANINGS: Final[Mapping[int, str]] = {
    EXIT_OK: "the command did what was asked",
    EXIT_FAILED: "the command ran and did not succeed",
    EXIT_USAGE: "the arguments were wrong; nothing ran",
    EXIT_CONFIGURATION: "the deployment is not configured for this; run 'ninjasre doctor'",
    EXIT_NOT_FOUND: "what was named does not exist",
    EXIT_DENIED: "this principal may not do this",
    EXIT_UNAVAILABLE: "a dependency the command needs could not be reached",
    EXIT_NEEDS_APPROVAL: "the change is gated and nobody has approved it",
    EXIT_INTERRUPTED: "somebody stopped it",
}


class CliError(Exception):
    """A failure the CLI reports, carrying the code it will exit with.

    Raised rather than returned so a command body reads as a straight line and
    the exit code is decided where the failure is understood, not by a caller
    inspecting a result and guessing.
    """

    def __init__(self, message: str, *, code: int = EXIT_FAILED, remedy: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.remedy = remedy

    def __str__(self) -> str:
        return f"{self.message} — {self.remedy}" if self.remedy else self.message


class ConfigurationError(CliError):
    """Something an operator has to set is unset or wrong."""

    def __init__(self, message: str, *, remedy: str = "run 'ninjasre doctor'") -> None:
        super().__init__(message, code=EXIT_CONFIGURATION, remedy=remedy)


class NotFoundError(CliError):
    """A run, a node, a schedule, or an integration that does not exist."""

    def __init__(self, message: str, *, remedy: str = "") -> None:
        super().__init__(message, code=EXIT_NOT_FOUND, remedy=remedy)


class DeniedError(CliError):
    """The acting principal is not permitted to do this."""

    def __init__(self, message: str, *, remedy: str = "") -> None:
        super().__init__(message, code=EXIT_DENIED, remedy=remedy)


class UnavailableError(CliError):
    """Something the command needs could not be reached."""

    def __init__(self, message: str, *, remedy: str = "") -> None:
        super().__init__(message, code=EXIT_UNAVAILABLE, remedy=remedy)


class ApprovalRequiredError(CliError):
    """A gated change that nobody has approved.

    Distinct from denied on purpose. "You may not" and "not yet" lead to
    different next actions, and a script that retried the first would loop.
    """

    def __init__(self, message: str, *, remedy: str = "approve it in the console or with /approve"):
        super().__init__(message, code=EXIT_NEEDS_APPROVAL, remedy=remedy)


def describe_exit_codes() -> str:
    """Return the exit-code contract as the CLI prints it."""
    width = max(len(str(code)) for code in EXIT_CODE_MEANINGS)
    return "\n".join(
        f"{code:>{width}}  {meaning}" for code, meaning in sorted(EXIT_CODE_MEANINGS.items())
    )


__all__ = [
    "EXIT_CODE_MEANINGS",
    "ApprovalRequiredError",
    "CliError",
    "ConfigurationError",
    "DeniedError",
    "NotFoundError",
    "UnavailableError",
    "describe_exit_codes",
]
