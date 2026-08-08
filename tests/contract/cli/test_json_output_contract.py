"""Every command's ``--json`` validates against a published schema.

Driven through the real typer application against an in-memory deployment, so
what is validated is what the command actually emits rather than a sample
somebody wrote beside the schema. Two assertions, and the first is the one that
keeps the second honest:

1. **Every command in the application has a published schema.** Walked from the
   typer app, so a command added without one fails here rather than shipping
   with an undocumented ``--json``.
2. **What it emits conforms.** Run, parsed, validated.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import chdir
from pathlib import Path

import pytest
from typer.testing import CliRunner

from config.constants.surfaces import EXIT_OK, JSON_ENVELOPE_KEYS
from surfaces.cli.app import app, use_local_services
from surfaces.cli.client import LocalClient
from surfaces.cli.output.schemas import COMMAND_SCHEMAS, published, validate
from tests.support.deployment import FakeServices, ScheduleSummary

pytestmark = pytest.mark.contract

#: One invocation of every command that produces a payload, with the arguments
#: it needs. Kept beside the schemas rather than generated, because "what does a
#: valid call to this command look like" is a fact about the command that no
#: introspection recovers.
INVOCATIONS: dict[str, list[str]] = {
    "investigate": ["investigate", "checkout latency doubled"],
    "runs.list": ["runs", "list"],
    "runs.show": ["runs", "show", "run-0001"],
    "runs.replay": ["runs", "replay", "run-0001"],
    "config.show": ["config", "show", "payments"],
    "config.set": ["config", "set", "settings.masking", "strict", "--node", "payments"],
    "config.diff": ["config", "diff", "payments", "root"],
    "schedule.list": ["schedule", "list"],
    "schedule.add": ["schedule", "add", "nightly sweep", "--cron", "0 2 * * *"],
    "schedule.remove": ["schedule", "remove", "job-001"],
    "estate.list": ["estate", "list"],
    "estate.summary": ["estate", "summary"],
    "estate.show": ["estate", "show", "res-guest"],
    "estate.maintain": ["estate", "maintain", "res-guest", "--reason", "replacing a disk"],
    "estate.release": ["estate", "release", "res-guest"],
    "incidents.list": ["incidents", "list"],
    "incidents.show": ["incidents", "show", "inc-0001"],
    "incidents.close": ["incidents", "close", "inc-0001", "--reason", "it was noise"],
    "incidents.suppress": [
        "incidents",
        "suppress",
        "inc-0001",
        "--rule",
        "rack-4-migration",
        "--reason",
        "the rack is being moved",
    ],
    "detectors.list": ["detectors", "list"],
    "detectors.observations": ["detectors", "observations"],
    "detectors.enable": ["detectors", "enable", "datastore-near-full"],
    "detectors.disable": ["detectors", "disable", "datastore-near-full"],
    "detectors.dry-run": ["detectors", "dry-run", "datastore-near-full"],
    "memory.search": ["memory", "search", "connection pool"],
    "memory.stats": ["memory", "stats"],
    "providers.list": ["providers", "list"],
    "providers.verify": ["providers", "verify", "anthropic"],
    "integrations.list": ["integrations", "list"],
    "integrations.health": ["integrations", "health"],
    "integrations.verify": ["integrations", "verify", "datadog"],
    "cost": ["cost"],
    "doctor": ["doctor"],
    "update": ["update"],
    "uninstall": ["uninstall", "--dry-run"],
}

#: Commands whose payload is asserted through their own module rather than
#: through the runner, because they prompt. Their schemas are still published
#: and still validated — see ``test_the_prompting_commands_still_conform``.
PROMPTING = {"onboard", "integrations.setup"}


def _walk(command: object, prefix: str = "") -> Iterator[str]:
    """Yield the dotted name of every leaf command in a typer application."""
    from typer.main import get_command

    click_command = get_command(command)  # type: ignore[arg-type]
    commands = getattr(click_command, "commands", None)
    if not commands:
        return
    for name, sub in commands.items():
        dotted = f"{prefix}{name}"
        children = getattr(sub, "commands", None)
        if children:
            for grandchild in children:
                yield f"{dotted}.{grandchild}"
        else:
            yield dotted


def application_commands() -> tuple[str, ...]:
    """Return every leaf command the CLI exposes, by its dotted name."""
    return tuple(sorted(_walk(app)))


def _run(
    services: FakeServices, arguments: Sequence[str], *, working_directory: Path | None = None
) -> dict[str, object]:
    """Run one command with ``--json`` and return the document it printed.

    Through the same registration a deployment profile uses, rather than by
    injecting a context object. A test that reached past the composition seam
    would pass on a build where the seam itself was broken.

    In an isolated working directory, because ``investigate`` writes its report
    to the current one — which is correct for an operator and would otherwise
    leave a file in the repository on every run of this suite.
    """
    elsewhere = working_directory or Path(tempfile.mkdtemp(prefix="ninjasre-cli-"))
    use_local_services(lambda: services)
    try:
        with chdir(elsewhere):
            result = CliRunner().invoke(app, ["--json", *arguments])
    finally:
        use_local_services(None)
    assert result.exit_code == EXIT_OK, f"{arguments}: exit {result.exit_code}\n{result.output}"
    return dict(json.loads(result.stdout))


def test_every_command_in_the_application_has_a_published_schema() -> None:
    # The assertion that keeps the rest honest. A command added without a schema
    # would otherwise simply not be tested.
    undocumented = [name for name in application_commands() if name not in COMMAND_SCHEMAS]

    assert not undocumented, f"these commands have no published --json schema: {undocumented}"


def test_every_published_schema_belongs_to_a_real_command() -> None:
    # The other direction: a schema for a command that no longer exists is a
    # published contract nothing honours.
    orphaned = [name for name in COMMAND_SCHEMAS if name not in application_commands()]

    assert not orphaned, f"these schemas describe no command: {orphaned}"


@pytest.mark.parametrize("command", sorted(INVOCATIONS))
def test_the_emitted_document_matches_its_published_schema(
    command: str, services: FakeServices, tmp_path: Path
) -> None:
    if command == "schedule.remove":
        # Needs something to remove. Created here rather than in the fixture so
        # the listing case still sees an empty schedule set.
        services.scheduled.setdefault("job-001", ScheduleSummary(job_id="job-001"))

    document = _run(services, INVOCATIONS[command], working_directory=tmp_path)

    assert tuple(sorted(document)) == tuple(sorted(JSON_ENVELOPE_KEYS))
    assert document["command"] == command
    validate(document["data"], COMMAND_SCHEMAS[command])


def test_the_schema_identifier_is_carried_in_the_document(services: FakeServices) -> None:
    document = _run(services, INVOCATIONS["memory.stats"])

    assert document["schema"] == published("memory.stats")["$id"]


def test_the_prompting_commands_still_conform(services: FakeServices) -> None:
    # ``onboard`` and ``integrations setup`` prompt, so they are driven through
    # the wizard rather than the runner. The payload is the same payload, and
    # skipping them here would leave two of the published schemas unasserted.
    import asyncio

    from surfaces.cli.wizard.flow import onboard
    from surfaces.cli.wizard.integrations import setup
    from surfaces.cli.wizard.prompts import ScriptedPrompter

    client = LocalClient(services=services)

    setup_outcome = asyncio.run(
        setup(client, "kubernetes", ScriptedPrompter(answers=["a-kubeconfig"]))
    )
    validate(setup_outcome.status.to_record(), COMMAND_SCHEMAS["integrations.setup"])

    onboarded = asyncio.run(
        onboard(
            client,
            ScriptedPrompter(answers=["a-key", "claude-sonnet-5", ""]),
            provider_id="anthropic",
        )
    )
    validate(onboarded.to_record(), COMMAND_SCHEMAS["onboard"])


def test_every_published_schema_is_covered_by_an_invocation() -> None:
    # A schema nothing exercises is a schema that can drift from the payload
    # without anything noticing.
    uncovered = set(COMMAND_SCHEMAS) - set(INVOCATIONS) - PROMPTING

    assert not uncovered, f"no invocation exercises: {sorted(uncovered)}"
