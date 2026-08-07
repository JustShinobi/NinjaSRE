"""Every slash command, and the property that all of them share.

**A slash command executes locally with no LLM call.** Not "usually", not "the
cheap ones": all sixteen, always. That is what makes ``/cost``
something you can type while wondering whether to keep going rather than
something that itself costs money.

The mechanism is that a command is handed a ``CommandContext`` with no model in
it. There is no client for a provider to reach, no runtime to invoke, no
capability registry to select from — so a command that wanted to call a model
would have to reach outside its arguments to find one, and the contract suite's
call counter is watching for exactly that.

``/help`` is generated from this registry rather than written down beside it. A
command whose help text lived in a separate document would be a command whose
help text is wrong within two releases.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import IO

from platform.observability.logging import get_logger
from surfaces.cli.client import PlatformClient
from surfaces.cli.output.degradation import PLAIN, Terminal
from surfaces.repl.interaction import InlineInteractions
from surfaces.repl.session import ReplSession, SessionStore

logger = get_logger(__name__)


@dataclass(slots=True)
class CommandContext:
    """Everything a slash command may touch.

    Deliberately without a model, a runtime, or a capability registry. A command
    can read run history and configuration through the platform client — those
    are reads, and they are how ``/runs`` and ``/integrations`` answer — but
    there is nothing here that could generate a token.
    """

    session: ReplSession
    out: IO[str]
    terminal: Terminal = PLAIN
    client: PlatformClient | None = None
    sessions: SessionStore | None = None
    interactions: InlineInteractions | None = None
    #: Set by ``/exit``. Read by the loop, which is the only thing that acts on
    #: it — a command that called ``sys.exit`` would take the session's unsaved
    #: state with it.
    should_exit: bool = False
    #: Set by ``/cancel``. The loop asks the runtime to stop at a safe point.
    cancel_requested: bool = False
    #: Set by ``/new`` and ``/resume``. The loop swaps the session in.
    switch_to: ReplSession | None = None

    def say(self, text: str) -> None:
        """Write one block of output to the session's terminal."""
        if text:
            self.out.write(text if text.endswith("\n") else text + "\n")


#: What a slash command is: a function over the context, returning nothing.
#: Synchronous by design — an async one would need a loop, and a loop is where
#: somebody would eventually await a model.
Handler = Callable[[CommandContext, str], None]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """One directive: its name, what it does, and how it is called."""

    name: str
    summary: str
    handler: Handler
    usage: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def invocation(self) -> str:
        """Return how ``/help`` shows this command being typed."""
        return f"/{self.name} {self.usage}".rstrip()


@dataclass(slots=True)
class Registry:
    """The catalogue of slash commands, and the only way one is dispatched."""

    commands: dict[str, SlashCommand] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict, repr=False)

    def register(self, command: SlashCommand) -> SlashCommand:
        """Add ``command`` and return it.

        Raises:
            ValueError: the name or one of the aliases is already taken. Two
                commands answering to one word is a coin toss at 03:00.
        """
        if command.name in self.commands or command.name in self._aliases:
            raise ValueError(f"/{command.name} is already registered")
        for alias in command.aliases:
            if alias in self.commands or alias in self._aliases:
                raise ValueError(f"/{alias} is already registered")

        self.commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name
        return command

    def find(self, name: str) -> SlashCommand | None:
        """Return the command ``name`` refers to, following aliases."""
        resolved = self._aliases.get(name, name)
        return self.commands.get(resolved)

    def names(self) -> tuple[str, ...]:
        """Return every command name, in alphabetical order."""
        return tuple(sorted(self.commands))

    def completions(self) -> tuple[str, ...]:
        """Return every word completion offers, aliases included."""
        return tuple(sorted(f"/{name}" for name in (*self.commands, *self._aliases)))

    def dispatch(self, context: CommandContext, name: str, arguments: str) -> bool:
        """Run the command called ``name`` and report whether one existed.

        Returns false rather than raising for an unknown name. Mistyping a slash
        command is an ordinary thing to do, and the loop's answer — a suggestion
        — is more useful than a traceback.
        """
        command = self.find(name)
        if command is None:
            return False
        logger.info("repl.slash_command", command=command.name)
        command.handler(context, arguments)
        return True

    def suggest(self, name: str, *, limit: int = 3) -> tuple[str, ...]:
        """Return the registered names closest to ``name``.

        Prefix and substring only. A fuzzy matcher would eventually suggest
        ``/cancel`` for ``/cost``, and a wrong suggestion during an incident is
        worse than none.
        """
        if not name:
            return ()
        prefixed = [known for known in self.names() if known.startswith(name)]
        contained = [known for known in self.names() if name in known and known not in prefixed]
        return (*prefixed, *contained)[:limit]

    def help_text(self, terminal: Terminal = PLAIN) -> str:
        """Return the command reference, generated from what is registered."""
        from surfaces.cli.output.tables import Column, table_of

        records: Sequence[Mapping[str, object]] = [
            {"command": self.commands[name].invocation, "does": self.commands[name].summary}
            for name in self.names()
        ]
        return table_of(
            records,
            (Column("Command", weight=2), Column("Does", weight=5)),
            terminal=terminal,
            title="Slash commands — every one of these runs locally, with no model call",
            empty="nothing is registered, which should not be possible",
        ).render(terminal)


def command(
    registry: Registry,
    name: str,
    summary: str,
    *,
    usage: str = "",
    aliases: Sequence[str] = (),
) -> Callable[[Handler], Handler]:
    """Return a decorator registering a handler under ``name``."""

    def register(handler: Handler) -> Handler:
        registry.register(
            SlashCommand(
                name=name,
                summary=summary,
                handler=handler,
                usage=usage,
                aliases=tuple(aliases),
            )
        )
        return handler

    return register


__all__ = [
    "CommandContext",
    "Handler",
    "Registry",
    "SlashCommand",
    "command",
]
