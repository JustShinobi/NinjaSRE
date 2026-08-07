"""Where a typed line goes, decided by one character and nothing else.

A line beginning with a literal ``/`` is a directive. **Everything else goes to
the agent.** There is no regex here, no keyword table, no "that looks like a
status request" shortcut, and adding one is the specific change this module
exists to make hard.

The reason is not stylistic. An intent shortcut answers without the agent, so:

- the answer is not in the trace, and Article I's claim that a conclusion
  carries its evidence quietly stops covering the answers that took the
  shortcut;
- the evaluation suite cannot score it, because the run it would have scored
  did not happen;
- the same words typed into the REPL, the console, and a chat thread produce
  different behaviour, and the difference is invisible until somebody compares
  two transcripts during an incident review.

The one exception is the literal prefix, and it is safe precisely because it is
not a guess: nobody types ``/`` at the start of a sentence by accident, and if
they do the failure is one unknown-command message rather than a silently
different investigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from config.constants.surfaces import SLASH_COMMAND_PREFIX


class Destination(StrEnum):
    """Where one line of input is going."""

    #: A locally-executed directive. No LLM call, ever.
    SLASH_COMMAND = "slash_command"

    #: The agent. Everything that is not a slash command.
    AGENT = "agent"

    #: Nothing. An empty line is not an instruction to do anything.
    NOTHING = "nothing"


@dataclass(frozen=True, slots=True)
class Action:
    """What one line of input turned out to be."""

    destination: Destination
    #: For a slash command, the name without its prefix. For the agent, the
    #: whole line as typed.
    body: str = ""
    arguments: str = ""

    @property
    def is_command(self) -> bool:
        """Return whether this line is a directive rather than something to investigate."""
        return self.destination is Destination.SLASH_COMMAND


def route(line: str) -> Action:
    """Return where ``line`` goes.

    Total, and deliberately dull. The whole rule is the absence of any
    branch here that inspects the content of a line that did not start with the
    prefix.
    """
    stripped = line.strip()
    if not stripped:
        return Action(destination=Destination.NOTHING)

    if not stripped.startswith(SLASH_COMMAND_PREFIX):
        # Not "does it look like a command". Not "is it short". The line goes to
        # the agent because it is not a slash command, which is the only test.
        return Action(destination=Destination.AGENT, body=line.strip())

    without_prefix = stripped[len(SLASH_COMMAND_PREFIX) :]
    name, _, arguments = without_prefix.partition(" ")
    if not name:
        # A bare slash. A command with no name, rather than a line for the
        # agent: routing it onward would make "/" mean two things.
        return Action(destination=Destination.SLASH_COMMAND, body="", arguments="")

    return Action(
        destination=Destination.SLASH_COMMAND,
        body=name.lower(),
        arguments=arguments.strip(),
    )


__all__ = ["Action", "Destination", "route"]
