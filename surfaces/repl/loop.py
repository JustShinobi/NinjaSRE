"""The interactive session: read a line, route it, show what happens.

Three things this owns that nothing else can.

**Whether there is anybody there.** With a TTY it starts; without one it says
so and exits. A REPL that blocked on a closed stdin turns a CI job into
a timeout, and the operator debugging that has no signal at all to work from.

**What Ctrl+C means.** During an investigation it cancels the investigation and
keeps the session; at an idle prompt it does nothing but clear the line. It is
never a kill: cancellation goes through the runtime's safe-point mechanism, so
a run stops between tool calls with its evidence written rather than mid-call
with its record saying "running" forever.

**Which session is live.** Slash commands set fields — ``switch_to``,
``should_exit``, ``cancel_requested`` — and the loop acts on them. Two places
deciding which session is current is one too many, and the one that loses is
the one holding the unsaved transcript.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import IO, Any, Protocol, runtime_checkable

from config.constants.paths import data_dir
from config.constants.surfaces import (
    CLI_COMMAND_NAME,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    REPL_CANCEL_GRACE_SECONDS,
)
from core.agent.interaction.registry import InteractionRegistry
from platform.observability.logging import get_logger
from surfaces.cli.errors import CliError
from surfaces.cli.invocation import Invocation
from surfaces.cli.output.degradation import Terminal
from surfaces.repl.commands import build_registry
from surfaces.repl.commands.registry import CommandContext, Registry
from surfaces.repl.input import InputClosed, Reader, build_reader
from surfaces.repl.interaction import InlineInteractions
from surfaces.repl.routing import Destination, route
from surfaces.repl.session import ReplSession, SessionStore
from surfaces.repl.streaming import StreamRenderer

logger = get_logger(__name__)

NO_TTY_MESSAGE = (
    "the interactive session needs a terminal.\n"
    f"Nothing is attached to this one, so there is nobody to prompt.\n"
    f"Run a command instead: {CLI_COMMAND_NAME} investigate 'what happened'\n"
    f"or see what there is: {CLI_COMMAND_NAME} --help"
)

BANNER = (
    "NinjaSRE. Describe an incident, or type /help.\n"
    "Anything that does not start with '/' goes to the agent."
)


def sessions_dir() -> Any:
    """Return where REPL sessions are stored."""
    return data_dir() / "sessions"


@runtime_checkable
class AgentDriver(Protocol):
    """What the loop needs to run and stop an investigation.

    A protocol because the REPL is tier 1 and composing a runtime is a
    deployment concern — and because it makes "what does Ctrl+C do mid-run" a
    test with a driver that records the cancel rather than one that needs a
    model.
    """

    async def start(self, session: ReplSession, objective: str) -> str:
        """Begin an investigation and return its run identifier."""

    async def drain(self, run_id: str, renderer: StreamRenderer) -> None:
        """Render events until the run finishes."""

    async def cancel(self, run_id: str) -> None:
        """Ask ``run_id`` to stop at its next safe point.

        Never a kill. The runtime decides where stopping is safe, which is what
        keeps the evidence gathered so far intact and the run's record honest.
        """

    async def finish(self, session: ReplSession, run_id: str) -> None:
        """Fold a finished run's result and accounting into ``session``."""


@dataclass(slots=True)
class Repl:
    """One interactive session, from the banner to the exit."""

    invocation: Invocation
    reader: Reader
    registry: Registry
    session: ReplSession
    sessions: SessionStore | None = None
    driver: AgentDriver | None = None
    interactions: InteractionRegistry = field(default_factory=InteractionRegistry)
    principal_id: str = ""

    @property
    def out(self) -> IO[str]:
        """Return the stream this session writes to."""
        return self.invocation.out

    @property
    def terminal(self) -> Terminal:
        """Return what this session's terminal can render."""
        return self.invocation.terminal

    def _context(self) -> CommandContext:
        """Return the context one slash command is handed.

        Built fresh per command. A long-lived one would let a command's field
        assignment survive into the next command, which is how ``/exit`` typed
        an hour ago ends a session somebody is still using.
        """
        self.interactions.run_id = self.session.active_run_id
        return CommandContext(
            session=self.session,
            out=self.out,
            terminal=self.terminal,
            client=self.invocation.client() if self._has_deployment() else None,
            sessions=self.sessions,
            interactions=InlineInteractions(
                registry=self.interactions,
                out=self.out,
                session=self.session,
                principal_id=self.principal_id,
                terminal=self.terminal,
            ),
        )

    def _has_deployment(self) -> bool:
        """Return whether a client can be resolved without failing."""
        try:
            self.invocation.client()
        except CliError:
            return False
        return True

    def say(self, text: str) -> None:
        """Write one block of output."""
        if text:
            self.out.write(text if text.endswith("\n") else text + "\n")

    # -- one line -------------------------------------------------------------

    def handle(self, line: str) -> bool:
        """Act on one line and return whether the session continues."""
        action = route(line)

        match action.destination:
            case Destination.NOTHING:
                return True
            case Destination.SLASH_COMMAND:
                return self._slash(action.body, action.arguments)
            case Destination.AGENT:
                self._to_agent(line.strip())
                return True

    def _slash(self, name: str, arguments: str) -> bool:
        """Run one slash command and return whether the session continues."""
        context = self._context()
        if not name:
            self.say("that is a slash with no command after it. Type /help.")
            return True

        try:
            known = self.registry.dispatch(context, name, arguments)
        except CliError as failed:
            self.say(f"{self.terminal.glyph('failed')} {failed}")
            return True

        if not known:
            suggestions = self.registry.suggest(name)
            hint = (
                f" Did you mean {', '.join('/' + found for found in suggestions)}?"
                if suggestions
                else ""
            )
            self.say(f"no such command: /{name}.{hint} Type /help.")
            return True

        if context.switch_to is not None:
            self._swap(context.switch_to)
        if context.cancel_requested:
            self._cancel()
        return not context.should_exit

    def _swap(self, session: ReplSession) -> None:
        """Make ``session`` the live one, saving whatever was live before."""
        if self.sessions is not None and session.session_id != self.session.session_id:
            self.sessions.save(self.session)
        self.session = session
        self.interactions = InteractionRegistry(run_id=session.active_run_id)
        for line in (session.objective,):
            self.reader.remember(line)

    def _to_agent(self, text: str) -> None:
        """Send one line to the agent and render what it does.

        Everything that is not a slash command comes here. There is no branch in
        front of this call, and adding one is the change ``surfaces/repl/AGENTS.md``
        exists to prevent.
        """
        self.session.record("human", text)
        if self.driver is None:
            self.say(
                "this session is not attached to a runtime, so there is nobody "
                "to investigate. Recorded in the transcript."
            )
            return

        renderer = StreamRenderer(out=self.out, terminal=self.terminal)
        try:
            run_id = self._run(self.driver.start(self.session, text))
            self.session.active_run_id = run_id
            self.interactions.run_id = run_id
            self._run(self.driver.drain(run_id, renderer))
        except KeyboardInterrupt:
            # The whole of the cancellation contract at this surface: cancel
            # the run, keep the session. A KeyboardInterrupt that reached the
            # top of the loop would end the session and lose the transcript.
            renderer.finish()
            self._cancel()
            return
        finally:
            renderer.finish()

        self._run(self.driver.finish(self.session, run_id))
        self.session.record(
            "agent", renderer.result, run_id=run_id, evidence=renderer.evidence_seen
        )
        self.session.active_run_id = ""

    def _cancel(self) -> None:
        """Ask the active run to stop, and say whether it did."""
        run_id = self.session.active_run_id
        if not run_id or self.driver is None:
            return

        self.say(f"stopping {run_id} at its next safe point…")
        try:
            self._run(asyncio.wait_for(self.driver.cancel(run_id), REPL_CANCEL_GRACE_SECONDS))
        except TimeoutError:
            # Reported rather than escalated to a kill. A run that will not stop
            # is a bug in the runtime, and killing the process here would hide
            # it behind a clean-looking exit.
            self.say(
                f"{run_id} has not stopped after {REPL_CANCEL_GRACE_SECONDS:.0f}s. "
                f"The session is still usable; check it with /runs show {run_id}."
            )
            return
        except KeyboardInterrupt:
            self.say("still stopping. The session is fine — press /exit to leave.")
            return

        logger.info("repl.run_cancelled", run_id=run_id, session_id=self.session.session_id)
        self.say(f"{run_id} stopped. The session is intact.")
        self.session.active_run_id = ""

    def _run[Result](self, work: Coroutine[Any, Any, Result]) -> Result:
        """Run one coroutine to completion."""
        return asyncio.run(work)

    # -- the loop -------------------------------------------------------------

    def run(self) -> int:
        """Read and act until the session ends, and return the process exit code."""
        self.say(BANNER)
        while True:
            try:
                line = self.reader.read()
            except InputClosed:
                # Ctrl+D. "I am finished", which is not the same as "stop what
                # you are doing" and does not cancel anything.
                self.say("")
                break
            except KeyboardInterrupt:
                # At an idle prompt there is nothing to cancel. Clearing the
                # line is what every shell does, and exiting would make Ctrl+C
                # a way to lose a session by muscle memory.
                self.say("")
                continue

            if not self.handle(line):
                break

        if self.sessions is not None:
            self.sessions.save(self.session)
        return EXIT_OK


def start(
    invocation: Invocation,
    *,
    driver: AgentDriver | None = None,
    reader: Reader | None = None,
    sessions: SessionStore | None = None,
    principal_id: str = "",
) -> int:
    """Start an interactive session and return the process exit code.

    Refuses without a terminal, and the message says what to run
    instead rather than only that this will not work — a refusal with no next
    step is a refusal somebody has to go and research.
    """
    if not invocation.terminal.interactive:
        invocation.write_error(NO_TTY_MESSAGE)
        logger.info("repl.refused_without_tty")
        return EXIT_UNAVAILABLE

    registry = build_registry()
    session = ReplSession(team_node_id=invocation.team_node_id)
    store = sessions if sessions is not None else SessionStore(directory=sessions_dir())

    repl = Repl(
        invocation=invocation,
        reader=reader or build_reader(registry.completions()),
        registry=registry,
        session=session,
        sessions=store,
        driver=driver,
        principal_id=principal_id,
    )
    logger.info("repl.started", session_id=session.session_id)
    return repl.run()


#: Kept so a composition root can hand the loop something to drive without the
#: loop importing it. Same reason ``LocalServices`` is a protocol.
DriverFactory = Callable[[Invocation], AgentDriver]


__all__ = [
    "BANNER",
    "NO_TTY_MESSAGE",
    "AgentDriver",
    "DriverFactory",
    "Repl",
    "sessions_dir",
    "start",
]
