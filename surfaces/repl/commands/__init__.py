"""The sixteen slash commands, registered into one catalogue.

Grouped by what they are for rather than one module per command: the session
commands share a store, the interaction commands share a registry, and splitting
them further would produce sixteen files with one function each and a shared
import block.

Every handler here is synchronous and takes no client it could reach a model
through. The guarantee is structural rather than a matter of discipline, and
``tests/contract/cli/test_slash_commands_are_local.py`` proves it by counting.
"""

from __future__ import annotations

from config.constants.surfaces import CLI_COMMAND_NAME
from surfaces.repl.commands.registry import (
    CommandContext,
    Handler,
    Registry,
    SlashCommand,
    command,
)
from surfaces.repl.commands.session_commands import register_session_commands
from surfaces.repl.commands.state_commands import register_state_commands


def build_registry() -> Registry:
    """Return the catalogue with every shipped command registered.

    Built rather than module-level, so a test gets a fresh one and two REPLs in
    one process do not share mutable state.
    """
    registry = Registry()
    register_state_commands(registry)
    register_session_commands(registry)

    @command(
        registry,
        "help",
        "Show this reference.",
        usage="",
        aliases=("?",),
    )
    def _help(context: CommandContext, arguments: str) -> None:
        """Show the command reference, generated from the registry itself."""
        if arguments:
            found = registry.find(arguments.strip().lstrip("/"))
            if found is None:
                context.say(f"no such command: /{arguments.strip()}")
                return
            context.say(f"{found.invocation}\n  {found.summary}")
            return
        context.say(registry.help_text(context.terminal))
        context.say(
            f"\nAnything that does not start with '/' goes to the agent.\n"
            f"Outside this session, the same things are '{CLI_COMMAND_NAME} <command>'."
        )

    return registry


__all__ = [
    "CommandContext",
    "Handler",
    "Registry",
    "SlashCommand",
    "build_registry",
    "command",
]
