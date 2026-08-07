"""A literal leading slash, and nothing else, makes a line a command.

The prohibition recorded in ``surfaces/repl/AGENTS.md``, asserted from the other
side: a battery of lines that a keyword matcher would have claimed, each of
which must reach the agent. If somebody adds an intent shortcut, these are the
tests that fail.
"""

from __future__ import annotations

import pytest

from surfaces.repl.routing import Destination, route

pytestmark = pytest.mark.unit

#: Lines a keyword or regex router would have intercepted. Every one of them is
#: something an engineer might actually type during an incident, and every one
#: of them goes to the agent.
WOULD_HAVE_BEEN_INTERCEPTED = [
    "status",
    "status?",
    "what is the status",
    "show me the status of the run",
    "cost",
    "how much has this cost",
    "help",
    "help me understand what happened to checkout",
    "runs",
    "list the runs from this morning",
    "exit",
    "the exit code was 137",
    "cancel",
    "cancel the deploy, not the investigation",
    "approve",
    "approve the rollback if you think it is safe",
    "model",
    "the model of the failure is a connection pool exhaustion",
    "resume",
    "resume the paused consumers",
    "compact",
    "the compaction job is behind",
    "new",
    "new pods are crashlooping",
    "takeover",
    "effort",
    "sessions",
    "integrations",
    "answer",
]


@pytest.mark.parametrize("line", WOULD_HAVE_BEEN_INTERCEPTED)
def test_a_line_that_looks_like_a_command_still_goes_to_the_agent(line: str) -> None:
    action = route(line)

    assert action.destination is Destination.AGENT, (
        f"{line!r} was routed away from the agent. That is the intent shortcut "
        f"surfaces/repl/AGENTS.md forbids: the answer would not be in the trace, "
        f"the evaluation suite could not score it, and the REPL would diverge "
        f"from every other surface."
    )
    assert action.body == line.strip()


@pytest.mark.parametrize(
    ("line", "name", "arguments"),
    [
        ("/help", "help", ""),
        ("/help runs", "help", "runs"),
        ("/approve abc123 approve", "approve", "abc123 approve"),
        ("  /status  ", "status", ""),
        ("/EXIT", "exit", ""),
        ("/answer  the pool was resized  ", "answer", "the pool was resized"),
    ],
)
def test_a_literal_prefix_is_the_only_thing_that_makes_a_command(
    line: str, name: str, arguments: str
) -> None:
    action = route(line)

    assert action.destination is Destination.SLASH_COMMAND
    assert action.body == name
    assert action.arguments == arguments


def test_a_bare_slash_is_a_command_with_no_name() -> None:
    # Not routed to the agent. "/" meaning two things is exactly the ambiguity
    # the literal rule exists to avoid.
    action = route("/")

    assert action.destination is Destination.SLASH_COMMAND
    assert action.body == ""


@pytest.mark.parametrize("line", ["", "   ", "\n", "\t  \n"])
def test_an_empty_line_is_not_an_instruction_to_do_anything(line: str) -> None:
    assert route(line).destination is Destination.NOTHING


def test_a_slash_inside_a_line_does_not_make_it_a_command() -> None:
    # A path, a fraction, a date. Only the *leading* character decides.
    for line in ("check /var/log/app", "the ratio was 3/4", "on 2026/03/14 at 14:02"):
        assert route(line).destination is Destination.AGENT, line


def test_a_command_name_is_lowercased_but_its_arguments_are_not() -> None:
    # Command names are matched case-insensitively; an argument is content and
    # is passed through exactly as typed.
    action = route("/ANSWER The Pool Was Resized")

    assert action.body == "answer"
    assert action.arguments == "The Pool Was Resized"


def test_routing_is_total() -> None:
    # Every line goes somewhere. A router with a fall-through nobody handled is
    # a router that silently drops input.
    for line in ("", "/", "/x", "x", "  ", "/x y", "x /y"):
        assert route(line).destination in set(Destination), line


def test_the_command_flag_agrees_with_the_destination() -> None:
    assert route("/help").is_command
    assert not route("help").is_command
    assert not route("").is_command
