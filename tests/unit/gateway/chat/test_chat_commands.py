"""Four platforms' command lists are generated from one catalogue.

The property that matters is not that the renderers work — it is that they
cannot drift. Every assertion here is about the *relationship* between the
catalogue and a rendering, so adding a command to the catalogue without touching
a renderer is the thing that keeps passing, and dropping one from a renderer is
the thing that fails.
"""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_PLATFORMS, CLI_COMMAND_NAME
from gateway.chat.commands import (
    COMMAND_CATALOGUE,
    COMMANDS,
    SLACK_COMMAND,
    find,
    help_text,
    parse,
    privileged_names,
    registration_for,
)
from platform.identity.permissions import Permission

pytestmark = pytest.mark.unit


# --- The catalogue itself -------------------------------------------------------


def test_every_command_is_uniquely_named() -> None:
    assert len({command.name for command in COMMAND_CATALOGUE}) == len(COMMAND_CATALOGUE)


def test_every_command_carries_a_summary_and_a_usage_line() -> None:
    for command in COMMAND_CATALOGUE:
        assert command.summary, command.name
        assert command.usage, command.name


def test_a_command_that_changes_something_names_the_permission_it_needs() -> None:
    """A privileged command with no permission would be one nothing refuses."""
    changing = {"investigate", "approve", "decline", "cancel"}

    for name in changing:
        command = find(name)
        assert command is not None
        assert command.requires is not None, name
        assert command.is_privileged is True


def test_a_read_only_command_deliberately_names_no_permission() -> None:
    status = find("status")
    assert status is not None
    assert status.requires is None
    assert status.is_privileged is False


def test_approving_needs_the_approval_permission_and_not_a_wider_one() -> None:
    approve = find("approve")
    assert approve is not None
    assert approve.requires is Permission.REMEDIATION_APPROVE


def test_the_privileged_set_is_derived_rather_than_listed_twice() -> None:
    assert set(privileged_names()) == {
        command.name for command in COMMAND_CATALOGUE if command.requires is not None
    }


def test_help_lists_every_command() -> None:
    listing = help_text()

    for command in COMMAND_CATALOGUE:
        assert command.name in listing


# --- The four renderings --------------------------------------------------------


@pytest.mark.parametrize("platform", CHAT_PLATFORMS)
def test_every_platform_has_a_registration_renderer(platform: str) -> None:
    assert registration_for(platform)


def test_an_unknown_platform_has_no_renderer_and_says_so() -> None:
    with pytest.raises(ValueError, match="no command registration renderer"):
        registration_for("irc")


def test_discord_registers_one_application_command_per_catalogue_row() -> None:
    registered = registration_for("discord")

    assert [row["name"] for row in registered] == [command.name for command in COMMAND_CATALOGUE]


def test_telegram_registers_one_command_per_catalogue_row() -> None:
    registered = registration_for("telegram")

    assert {row["command"] for row in registered} == set(COMMANDS)


def test_teams_declares_one_manifest_entry_per_catalogue_row() -> None:
    registered = registration_for("microsoft_teams")

    assert {row["title"] for row in registered} == set(COMMANDS)


def test_slack_registers_one_command_whose_hint_names_the_subcommands() -> None:
    """Slack takes a command, not a command tree, so the names are its arguments."""
    registered = registration_for("slack")

    assert len(registered) == 1
    assert registered[0]["command"] == SLACK_COMMAND
    assert f"/{CLI_COMMAND_NAME}" == SLACK_COMMAND
    for command in COMMAND_CATALOGUE:
        assert command.name in registered[0]["usage_hint"]


def test_a_discord_command_with_arguments_declares_an_option_for_them() -> None:
    registered = {row["name"]: row for row in registration_for("discord")}

    assert registered["approve"]["options"]
    assert registered["status"]["options"] == ()


# --- Parsing --------------------------------------------------------------------


def test_a_slash_prefixed_catalogue_name_is_a_command() -> None:
    assert parse("/status") == ("status", "")
    assert parse("/approve i-1") == ("approve", "i-1")


def test_a_command_addressed_to_a_bot_is_still_the_command() -> None:
    """Telegram addresses a command in a group as ``/status@thebot``."""
    assert parse("/status@ninjasre_bot") == ("status", "")


def test_something_that_is_not_in_the_catalogue_is_not_a_command() -> None:
    assert parse("/deploy-everything") == ("", "")


def test_a_sentence_that_merely_reads_like_one_is_not_a_command() -> None:
    """A literal prefix and nothing else — no 'looks like a command' heuristic."""
    assert parse("can you approve the rollback") == ("", "")
    assert parse("status?") == ("", "")


def test_parsing_accepts_a_platform_specific_prefix() -> None:
    assert parse("!status", prefixes=("!",)) == ("status", "")
