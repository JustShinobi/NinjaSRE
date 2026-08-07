"""One command catalogue, rendered four ways.

Slash commands and application commands are *generated* from a shared catalogue
rather than declared per platform. Four hand-maintained command
lists drift within a release, and the drift is invisible — Slack's ``/ninjasre
status`` keeps working while Discord's ``/status`` quietly stopped being
registered, and nobody finds out until somebody types it during an incident.

So a command is a row here, carrying the permission it needs, and each adapter
turns the same rows into its own registration payload. Adding a command is one
row; adding a platform is one renderer.

**Every privileged command names its permission.** A command with no permission
is a read, and ``requires`` being ``None`` is the explicit statement of that
rather than an omission — the same shape ``gateway/http/security`` uses for a
public route.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from config.constants.surfaces import (
    CHAT_PLATFORM_DISCORD,
    CHAT_PLATFORM_MICROSOFT_TEAMS,
    CHAT_PLATFORM_SLACK,
    CHAT_PLATFORM_TELEGRAM,
    CLI_COMMAND_NAME,
)
from platform.identity.permissions import Permission

#: The Slack slash command every subcommand is issued under. Slack registers one
#: command per app in the common case, so the shared names become its first
#: argument rather than separate registrations.
SLACK_COMMAND = f"/{CLI_COMMAND_NAME}"


@dataclass(frozen=True, slots=True)
class ChatCommand:
    """One thing somebody can ask the bot to do, on any platform."""

    name: str
    summary: str
    usage: str = ""
    #: The permission this needs, or ``None`` when it changes nothing.
    requires: Permission | None = None

    @property
    def is_privileged(self) -> bool:
        """Return whether an unmapped user must be refused this."""
        return self.requires is not None

    def describe(self) -> str:
        """Return the one line a help listing shows."""
        return f"{self.name} — {self.summary}"


COMMAND_CATALOGUE: Final[tuple[ChatCommand, ...]] = (
    ChatCommand(
        name="investigate",
        summary="start an investigation in this thread",
        usage="investigate <what is wrong>",
        requires=Permission.INVESTIGATION_RUN,
    ),
    ChatCommand(
        name="status",
        summary="show what the run in this thread is doing",
        usage="status",
    ),
    ChatCommand(
        name="report",
        summary="post the report for the run in this thread",
        usage="report",
        requires=Permission.REPORT_READ,
    ),
    ChatCommand(
        name="approvals",
        summary="list what is waiting on a decision",
        usage="approvals",
        requires=Permission.APPROVAL_READ,
    ),
    ChatCommand(
        name="approve",
        summary="approve a proposed change",
        usage="approve <approval id>",
        requires=Permission.REMEDIATION_APPROVE,
    ),
    ChatCommand(
        name="decline",
        summary="decline a proposed change, with a reason",
        usage="decline <approval id> <reason>",
        requires=Permission.REMEDIATION_APPROVE,
    ),
    ChatCommand(
        name="cancel",
        summary="ask the run in this thread to stop at its next safe point",
        usage="cancel",
        requires=Permission.INVESTIGATION_RUN,
    ),
    ChatCommand(
        name="help",
        summary="list what this bot understands",
        usage="help",
    ),
)

COMMANDS: Final[Mapping[str, ChatCommand]] = {
    command.name: command for command in COMMAND_CATALOGUE
}


def find(name: str) -> ChatCommand | None:
    """Return the command ``name`` refers to, or ``None``."""
    return COMMANDS.get(name.strip().lstrip("/").lower())


def help_text() -> str:
    """Return the listing ``help`` answers with, on every platform."""
    return "\n".join(f"• {command.describe()}" for command in COMMAND_CATALOGUE)


def registration_for(platform: str) -> tuple[Mapping[str, Any], ...]:
    """Return the command registration payload ``platform`` expects.

    Raises:
        ValueError: ``platform`` is not one of the four.
    """
    if platform == CHAT_PLATFORM_SLACK:
        return _slack()
    if platform == CHAT_PLATFORM_DISCORD:
        return _discord()
    if platform == CHAT_PLATFORM_TELEGRAM:
        return _telegram()
    if platform == CHAT_PLATFORM_MICROSOFT_TEAMS:
        return _teams()
    raise ValueError(f"{platform!r} has no command registration renderer")


def _slack() -> tuple[Mapping[str, Any], ...]:
    """Return the one Slack slash command, and the subcommands it accepts.

    Slack's app manifest declares a command, not a command tree, so the shared
    names are documented in the hint rather than registered individually.
    """
    return (
        {
            "command": SLACK_COMMAND,
            "description": "Investigate, approve, and check on NinjaSRE from Slack",
            "usage_hint": " | ".join(command.name for command in COMMAND_CATALOGUE),
            "should_escape": False,
        },
    )


def _discord() -> tuple[Mapping[str, Any], ...]:
    """Return one Discord application command per catalogue row."""
    return tuple(
        {
            "name": command.name,
            "description": command.summary,
            "type": 1,
            "options": _discord_options(command),
        }
        for command in COMMAND_CATALOGUE
    )


def _discord_options(command: ChatCommand) -> tuple[Mapping[str, Any], ...]:
    """Return the free-text option a command with arguments takes."""
    _, _, arguments = command.usage.partition(" ")
    if not arguments:
        return ()
    return (
        {
            "name": "arguments",
            "description": arguments.strip("<>"),
            "type": 3,
            "required": False,
        },
    )


def _telegram() -> tuple[Mapping[str, Any], ...]:
    """Return the ``setMyCommands`` payload, which is name and description only."""
    return tuple(
        {"command": command.name, "description": command.summary} for command in COMMAND_CATALOGUE
    )


def _teams() -> tuple[Mapping[str, Any], ...]:
    """Return the command list a Teams app manifest declares."""
    return tuple(
        {"title": command.name, "description": command.summary} for command in COMMAND_CATALOGUE
    )


def privileged_names() -> tuple[str, ...]:
    """Return the commands an unmapped user must be refused."""
    return tuple(command.name for command in COMMAND_CATALOGUE if command.is_privileged)


def parse(text: str, *, prefixes: Sequence[str] = ("/",)) -> tuple[str, str]:
    """Return the ``(command, arguments)`` ``text`` spells, or two empty strings.

    A literal prefix and nothing else, for the reason ``surfaces/repl`` states
    for the same decision: a "looks like a command" heuristic eventually reads
    somebody's sentence as an instruction to the deployment.
    """
    stripped = text.strip()
    for prefix in prefixes:
        if not stripped.startswith(prefix):
            continue
        body = stripped[len(prefix) :]
        head, _, rest = body.partition(" ")
        # ``/status@ninjasre_bot`` — Telegram addresses a command in a group.
        name = head.partition("@")[0].lower()
        if name in COMMANDS:
            return name, rest.strip()
        return "", ""
    return "", ""


__all__ = [
    "COMMANDS",
    "COMMAND_CATALOGUE",
    "SLACK_COMMAND",
    "ChatCommand",
    "find",
    "help_text",
    "parse",
    "privileged_names",
    "registration_for",
]
