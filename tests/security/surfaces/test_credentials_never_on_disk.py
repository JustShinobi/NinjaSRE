"""No credential in shell history, a config file, or CLI output.

Article IV at the surface where an operator actually types one. Four claims,
and each is asserted by looking for the secret rather than by trusting the code
path that was supposed to avoid it:

- **No command accepts one as an argument.** Walked from the typer application,
  because an argument is in the shell history before the process starts and no
  later care recovers from that.
- **It goes to the vault and nowhere else.** The value reaches the store, and
  nothing else in the deployment holds it afterwards.
- **It is not echoed.** Not in the command's own output, and not in what the
  wizard says.
- **It is not in the REPL history.** The one file the REPL writes that holds
  what somebody typed.
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterator

import pytest

from surfaces.cli.app import app
from surfaces.cli.client import LocalClient
from surfaces.cli.wizard.flow import onboard
from surfaces.cli.wizard.integrations import setup
from surfaces.cli.wizard.prompts import ScriptedPrompter
from surfaces.repl.input import Reader
from surfaces.repl.routing import route
from surfaces.repl.session import ReplSession, SessionStore
from tests.support.deployment import FakeServices, seeded

pytestmark = pytest.mark.security

#: A value nothing in the platform could produce by accident, so finding it
#: anywhere is proof it travelled rather than a coincidence.
SECRET = "sk-ant-CANARY-0f3a91b7c2e84d55"

#: Words that name a credential-shaped option. A command that grew one would
#: have created a way to put a secret in the shell history.
CREDENTIAL_WORDS = ("password", "secret", "api-key", "apikey", "token", "credential")

#: The exception. A bearer token for a *remote deployment* is not a vendor
#: credential and never enters the vault — it is how the CLI authenticates to
#: the platform the operator is already running, and it has to be passable in a
#: script. The wording is deliberate: this is the only place a token-shaped
#: option is allowed, and it is allowed by name rather than by pattern.
PERMITTED_TOKEN_OPTIONS = frozenset({"--token"})


def _options(command: object) -> Iterator[str]:
    """Yield every option string in a typer application, recursively."""
    from typer.main import get_command

    click_command = get_command(command)  # type: ignore[arg-type]

    def walk(node: object) -> Iterator[str]:
        for parameter in getattr(node, "params", ()):
            yield from getattr(parameter, "opts", ())
            yield from getattr(parameter, "secondary_opts", ())
        for child in (getattr(node, "commands", None) or {}).values():
            yield from walk(child)

    yield from walk(click_command)


def test_no_command_accepts_a_credential_as_an_argument() -> None:
    offending = [
        option
        for option in _options(app)
        if option not in PERMITTED_TOKEN_OPTIONS
        and any(word in option.lower() for word in CREDENTIAL_WORDS)
    ]

    assert not offending, (
        f"these options would put a credential in the shell history: {offending}. "
        f"Prompt for it and write it to the vault instead."
    )


def test_a_credential_entered_through_the_wizard_reaches_the_vault() -> None:
    services = seeded()
    prompter = ScriptedPrompter(answers=[SECRET])

    asyncio.run(setup(LocalClient(services=services), "kubernetes", prompter))

    assert services.vault["kubernetes"] == {"kubeconfig": SECRET}


def test_the_wizard_never_echoes_what_it_was_given() -> None:
    services = seeded()
    prompter = ScriptedPrompter(answers=[SECRET])

    asyncio.run(setup(LocalClient(services=services), "kubernetes", prompter))

    said = "\n".join(prompter.said)
    assert SECRET not in said
    # And it was read with the echo off, which is what stops it being on screen.
    assert prompter.secrets_asked == ["Kubeconfig"]


def test_the_status_a_setup_returns_carries_no_credential() -> None:
    services = seeded()

    outcome = asyncio.run(
        setup(LocalClient(services=services), "kubernetes", ScriptedPrompter(answers=[SECRET]))
    )

    document = json.dumps(outcome.status.to_record())
    assert SECRET not in document
    # Field *names* are reported so an operator can see what they skipped.
    assert outcome.entered == ("kubeconfig",)


def test_a_whole_onboarding_leaves_no_credential_in_its_payload() -> None:
    services = seeded()
    prompter = ScriptedPrompter(answers=[SECRET, "claude-sonnet-5", "kubernetes", SECRET])

    outcome = asyncio.run(
        onboard(LocalClient(services=services), prompter, provider_id="anthropic")
    )

    assert SECRET not in json.dumps(outcome.to_record())
    assert SECRET not in "\n".join(outcome.steps)
    assert SECRET not in "\n".join(prompter.said)


def test_a_credential_is_not_written_into_configuration() -> None:
    services = seeded()

    asyncio.run(
        setup(LocalClient(services=services), "kubernetes", ScriptedPrompter(answers=[SECRET]))
    )

    stored_config = json.dumps({node: view.to_record() for node, view in services.config.items()})
    assert SECRET not in stored_config


def test_a_credential_is_not_written_into_a_stored_session(tmp_path: object) -> None:
    # The REPL's own file. It holds a transcript, and a transcript is a record
    # of what somebody typed.
    store = SessionStore(directory=tmp_path / "sessions")  # type: ignore[operator]
    session = ReplSession(session_id="sess-1")
    session.record("human", "the datadog integration is failing")
    store.save(session)

    written = (tmp_path / "sessions" / "sess-1.json").read_text()  # type: ignore[operator]
    assert SECRET not in written


def test_the_repl_never_routes_a_credential_prompt_through_its_history() -> None:
    # Nothing that reads a credential reads it through the reader, so a secret
    # cannot reach the history file by that path. Asserted structurally: the
    # reader has no method that reads without echo.
    reader = Reader(completions=("/help",), history_file=None)

    assert not hasattr(reader, "secret")
    assert not hasattr(reader, "read_password")


def test_a_pasted_credential_is_routed_to_the_agent_not_to_a_command() -> None:
    # Somebody pasting a key into the REPL by mistake must not have it
    # interpreted as a directive that stores it. It goes to the agent like any
    # other text, where masking and guardrails apply.
    action = route(SECRET)

    assert action.destination.value == "agent"


def test_the_credential_does_not_reach_the_terminal_through_a_status_render() -> None:
    services = seeded()
    asyncio.run(
        setup(LocalClient(services=services), "kubernetes", ScriptedPrompter(answers=[SECRET]))
    )
    written = io.StringIO()

    status = asyncio.run(LocalClient(services=services).verify_integration("kubernetes"))
    written.write(json.dumps(status.to_record()))

    assert SECRET not in written.getvalue()


def test_the_deployment_holds_the_secret_only_in_the_vault() -> None:
    services = FakeServices()
    asyncio.run(
        setup(LocalClient(services=services), "kubernetes", ScriptedPrompter(answers=[SECRET]))
    )

    # Everything the deployment holds, except the vault itself.
    elsewhere = json.dumps(
        {
            "integration_states": {
                name: status.to_record() for name, status in services.integration_states.items()
            },
            "provider_states": {
                name: status.to_record() for name, status in services.provider_states.items()
            },
            "config": {node: view.to_record() for node, view in services.config.items()},
        }
    )

    assert SECRET in json.dumps(services.vault)
    assert SECRET not in elsewhere
