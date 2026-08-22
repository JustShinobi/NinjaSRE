"""The guided first run, held against the platform it is a view of.

Two surfaces walk an operator through the same setup — ``ninjasre onboard`` in a
terminal and the console's first-run area in a browser — and the requirement is
that they *agree*. The way they agree is not that somebody kept two
implementations in step: it is that neither implements anything. Both move one
document, ``GET /v1/setup/checklist``, and both read their state out of it.

So the tests here are about that single source rather than about two renderings.
The CLI is driven against a real application, the document is fetched over HTTP
afterwards, and what the console derives from a document is held against the
vocabulary the platform actually spells — because a console branching on a word
nothing emits is a console that shows the wrong step and passes its own suite.

The TypeScript is read as source. That is the same technique the rest of the
console contract suite uses, and it is here for the same reason: a Python test
cannot import a browser module, and a claim nobody checks in either language is
a claim that drifts.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Final

import pytest

from config.constants.first_run import (
    SETUP_READINESS,
    SETUP_READINESS_ABSENT,
    SETUP_READINESS_CONFIGURED,
    SETUP_STATES,
    SETUP_STEP_FIRST_INVESTIGATION,
    SETUP_STEP_INFRASTRUCTURE_SOURCE,
    SETUP_STEP_ORDER,
)
from config.constants.llm import DEFAULT_MODEL_ID
from gateway.http.credential_schemas import schema_for
from integrations._catalogue.discovery import catalogue
from platform.config_service.schema.root import RootConfig
from surfaces.cli.client import RemoteClient
from surfaces.cli.wizard.flow import onboard
from tests.contract.cli.test_onboarding_against_a_deployment import (  # noqa: F401
    SECRET,
    _Deployment,
    _prompter,
    deployment,
    remote,
)

pytestmark = pytest.mark.contract


def console_root() -> Path:
    """Return the console directory."""
    return Path(__file__).resolve().parents[3] / "console"


PLAN: Final = console_root() / "src" / "surfaces" / "first-run" / "plan.ts"
SCREEN: Final = console_root() / "src" / "surfaces" / "screens" / "first-run.tsx"
DASHBOARD: Final = console_root() / "src" / "surfaces" / "screens" / "dashboard.tsx"
SHELL_LOAD: Final = console_root() / "src" / "shell" / "load.ts"
TUTORIAL: Final = console_root() / "src" / "surfaces" / "first-run" / "tutorial-setting.ts"
MODEL_STEP: Final = console_root() / "src" / "surfaces" / "first-run" / "model.tsx"


def _source(path: Path) -> str:
    assert path.exists(), f"{path} is not there"
    return path.read_text(encoding="utf-8")


# --- The two surfaces, one document -------------------------------------------------


def test_the_cli_and_the_console_read_one_checklist(
    remote: RemoteClient,  # noqa: F811
    deployment: _Deployment,  # noqa: F811
) -> None:
    """``onboard`` moves the document; the console's derivation reads that document.

    The agreement is structural rather than asserted twice. What is checked here
    is that the guided run in a terminal changes what the *route* answers, and
    that every field the console's reader picks out of that answer is in it —
    which is what makes "close the browser, run the CLI, come back" produce one
    consistent screen rather than two opinions.
    """
    before = deployment.run(
        deployment.http.get(
            "/v1/setup/checklist",
            headers={"authorization": f"Bearer {deployment.token}"},
        )
    ).json()
    assert before["provider"] == "absent"
    assert before["complete"] is False

    outcome = asyncio.run(onboard(remote, _prompter(), provider_id="anthropic"))
    assert outcome.verified, outcome.detail

    after = deployment.run(
        deployment.http.get(
            "/v1/setup/checklist",
            headers={"authorization": f"Bearer {deployment.token}"},
        )
    ).json()

    # The terminal moved it, and the browser would see the move: provider
    # readiness is the field the console's step derivation turns on, and it is
    # no longer where a fresh deployment leaves it.
    assert after["provider"] != before["provider"]
    assert after["provider"] != "absent"
    # And it moved to the *middle* value rather than to the last one, because
    # the route composes no live verifier. A stored key that nobody has checked
    # from this process is exactly the state the three-word vocabulary exists
    # for, and the console has to show it as such rather than as finished.
    assert after["provider"] == SETUP_READINESS_CONFIGURED

    # Every field the console's reader takes out of this document is here. A
    # console reading a key the route stopped sending would derive step one
    # forever, on a deployment that had finished.
    for key in ("complete", "steps", "next", "provider", "integrations"):
        assert key in after, f"the checklist answers no {key}, and the console reads it"
    for step in after["steps"]:
        assert {"name", "state", "detail", "action"} <= set(step)
    assert {step["name"] for step in after["steps"]} == set(SETUP_STEP_ORDER)


def test_the_model_the_cli_wrote_is_the_setting_the_console_writes(
    remote: RemoteClient,  # noqa: F811
) -> None:
    """One configuration path for the model, whichever surface chose it."""
    outcome = asyncio.run(onboard(remote, _prompter(), provider_id="anthropic"))

    assert outcome.model_id == DEFAULT_MODEL_ID
    written = re.findall(r"MODEL_SETTING = '([^']+)'", _source(PLAN))
    assert written == ["models.investigator.model"], (
        "the console writes the model somewhere the platform does not resolve it from"
    )


# --- What the console is allowed to branch on ----------------------------------------


def test_the_console_branches_only_on_readiness_words_the_platform_declares() -> None:
    """A word nothing emits is a step the screen shows forever."""
    source = _source(PLAN)
    compared = set(re.findall(r"(?:provider|readiness) (?:!==|===) '([a-z-]+)'", source))
    compared |= set(re.findall(r"readiness === '([a-z-]+)'", source))

    unknown = compared - set(SETUP_READINESS)
    assert not unknown, (
        f"{sorted(unknown)} is not a readiness this platform reports; it declares "
        f"{', '.join(SETUP_READINESS)}"
    )
    # And it has to use more than one of them, or the three-valued vocabulary is
    # being collapsed back into a boolean by the one surface it was added for.
    assert len(compared & set(SETUP_READINESS)) >= 2


def test_the_console_branches_only_on_step_states_the_platform_declares() -> None:
    """The same, for the step vocabulary."""
    source = _source(PLAN)
    compared = set(re.findall(r"stateOfStep\([^)]*\) === '([a-z-]+)'", source))

    unknown = compared - set(SETUP_STATES)
    assert not unknown, f"{sorted(unknown)} is not a checklist state this platform reports"


def test_the_console_names_the_checklist_steps_the_platform_names() -> None:
    """Two of the four are what the last two wizard steps hand over to."""
    source = _source(PLAN)
    named = set(re.findall(r"STEP = '([a-z-]+)'", source))

    assert SETUP_STEP_INFRASTRUCTURE_SOURCE in named
    assert SETUP_STEP_FIRST_INVESTIGATION in named
    unknown = named - set(SETUP_STEP_ORDER)
    assert not unknown, f"{sorted(unknown)} is not a checklist step this platform reports"


def test_the_progress_count_is_not_recomputed_from_the_console_s_own_wizard_steps() -> None:
    """`outstanding` reads the deployment's own steps, not a client-only tally.

    The seven wizard steps are a UI sequencing concept with no counterpart in
    the document this route answers — the checklist has its own steps, in its
    own vocabulary, and a count built by filtering the wizard's seven against
    ad hoc client rules is a count the CLI has no way to reproduce. `outstanding`
    is required to read `setup.steps` — the array this document actually
    carries — rather than the `WIZARD_STEPS` constant, so the same document
    that decides the CLI's view decides this one too.
    """
    source = _source(PLAN)
    body = re.search(
        r"function outstanding\(setup: DeploymentSetup\): number \{(.*?)\n\}", source, re.DOTALL
    )
    assert body is not None, "plan.ts declares no outstanding(setup) function to inspect"
    assert "WIZARD_STEPS" not in body.group(1), (
        "outstanding() still tallies the client-only WIZARD_STEPS list rather than reading "
        "setup.steps, the array the checklist route actually serves"
    )
    assert "setup.steps" in body.group(1), (
        "outstanding() does not read setup.steps, so it has no server-reported state to count"
    )


def test_the_checklist_heading_is_not_a_second_tally_beside_outstanding() -> None:
    """The heading and the progress line are one claim, not two.

    `outstanding()` above is the single source the progress line reads. The
    heading beside it picked its label — "What is left" versus "Every step is
    done" — by comparing the console's own seven-screen tally against
    `WIZARD_STEPS.length`, a second count with a different denominator than
    `outstanding()`'s (the checklist route's own steps, five today). The two
    can disagree by construction, which is the "2 of 7" and "3 outstanding"
    shown together that this feature exists to end. The heading has to be
    picked from the same numbers the progress line already reads.
    """
    source = _source(SCREEN)
    marker = "checklistTitle("
    start = source.find(marker)
    assert start != -1, "first-run.tsx no longer heads the checklist panel with checklistTitle"
    call = source[start : source.find(";", start)]
    assert "WIZARD_STEPS" not in call, (
        "checklistTitle() is still called with WIZARD_STEPS.length — the console's own "
        "seven-screen tally — rather than with the numbers outstanding() and the progress "
        "line already read from setup.steps"
    )
    assert "outstanding(" in call, (
        "checklistTitle() is not called with outstanding(setup), so its label is not drawn "
        "from the single source of progress"
    )


# --- One source, and no second one ----------------------------------------------------


@pytest.mark.parametrize("module", ["screen", "dashboard", "shell"])
def test_setup_state_is_read_from_the_checklist_route_and_nowhere_else(module: str) -> None:
    """A second source of "are we set up" is the one that disagrees at 03:00."""
    source = _source({"screen": SCREEN, "dashboard": DASHBOARD, "shell": SHELL_LOAD}[module])
    assert "/v1/setup/checklist" in source, "this surface shows setup state and never asks"
    assert "/v1/setup/self-check" not in source, (
        "the self-check is a diagnosis, not a checklist. Two answers to 'are we set up' "
        "is one more than a console may hold."
    )


def test_the_provider_step_is_drawn_from_the_descriptors_rather_than_a_list() -> None:
    """Nine providers with equal weight is a property of reading, not of copying."""
    source = _source(SCREEN)
    assert "'/v1/providers'" in source
    for named in ("anthropic", "openai", "ollama"):
        assert f"'{named}'" not in source, (
            f"the first-run screen names {named}. Article VI is about the screen where "
            "somebody chooses, and a screen with a provider's name in it has an opinion "
            "about which of the nine matters."
        )


# --- The settings the guided run writes exist ------------------------------------------


def test_every_setting_the_guided_run_writes_is_one_the_schema_declares() -> None:
    """A patch at a path nothing resolves is configuration nobody ever reads."""
    paths = set(re.findall(r"SETTING = '([a-z_.]+)'", _source(PLAN)))
    paths |= set(re.findall(r"TUTORIAL_SETTING = '([a-z_.]+)'", _source(TUTORIAL)))
    assert paths, "the guided run writes nothing, which cannot be right"

    for path in sorted(paths):
        section: object = RootConfig()
        for part in path.split("."):
            assert hasattr(section, part), (
                f"{path} is written by the console and {part} is not in the configuration "
                "schema; the write would be silently ignored"
            )
            section = getattr(section, part)


def test_the_model_step_writes_the_provider_alongside_the_model() -> None:
    """A model saved without its provider resolves against whatever was there before.

    The two settings are one decision. Writing only the model would leave a
    deployment pointing a Bedrock model identifier at whichever provider the
    node happened to inherit, which fails at the first request and reads as the
    model being wrong.
    """
    source = _source(PLAN)
    assert "MODEL_PROVIDER_SETTING" in source and "MODEL_SETTING" in source

    # The function that grows the patch, whatever it is called and however the
    # document is built. Matching a literal `const patch = {...}` made this
    # test a statement about one spelling: it went quiet the moment the patch
    # moved into a builder, and the setting it exists to protect could have
    # been dropped without a word.
    built = re.search(r"function patchOf\((.*?)\n\}", _source(MODEL_STEP), re.DOTALL)
    assert built is not None, "the model step has no patch builder to inspect"
    assert "MODEL_PROVIDER_SETTING" in built.group(1)
    assert "MODEL_SETTING" in built.group(1)
    assert "patchOf(" in _source(MODEL_STEP), "the builder is never called"


# --- The outcome the guided run is for, through the routes the console calls ----------


def test_a_credential_written_the_way_the_console_writes_it_verifies(
    deployment: _Deployment,  # noqa: F811
) -> None:
    """The two routes the console's couriers call, against a real deployment.

    The browser suite proves the console reaches these routes and renders what
    they answer; its backing is a recorded dataset and cannot verify anything.
    This is the other half of the same claim, and it is deliberately made with
    the *same requests* the couriers issue rather than through the CLI wizard:
    a ``PUT`` of a flat credential map, then a ``POST`` to verify, for an
    integration rather than for the provider.

    "Configured" and "verified" stay apart throughout. The write reports the
    first and the check reports the second, and the assertion below is that the
    second came back true — which is the half of the definition of done that a
    fixture saying ``usable: true`` could not establish.
    """
    headers = {"authorization": f"Bearer {deployment.token}"}
    name = next(entry.name for entry in catalogue())

    before = deployment.run(
        deployment.http.post(f"/v1/integrations/{name}/verify", headers=headers)
    ).json()
    assert before["usable"] is False, "nothing is stored yet, so nothing can be usable"

    schema = schema_for(name)
    values = {field.name: _plausible(field) for field in schema.fields}
    written = deployment.run(
        deployment.http.put(
            f"/v1/integrations/{name}/credential", headers=headers, json={"values": values}
        )
    )
    assert written.status_code == 200, written.text
    # Field names and a version, and no field a value could sit in.
    assert set(written.json()) == {"integration", "state", "usable", "version", "fields"}
    assert written.json()["fields"] == sorted(values)
    for secret in values.values():
        assert secret not in written.text

    after = deployment.run(
        deployment.http.post(f"/v1/integrations/{name}/verify", headers=headers)
    ).json()
    assert after["usable"] is True, after
    assert after["integration"] == name

    # And the checklist the console reads now reports that integration as
    # holding something, which is what moves the console's own verify step.
    checklist = deployment.run(deployment.http.get("/v1/setup/checklist", headers=headers)).json()
    readiness = {entry["name"]: entry["readiness"] for entry in checklist["integrations"]}
    assert readiness.get(name) != SETUP_READINESS_ABSENT, readiness


def _plausible(field: object) -> str:
    """Return a value that satisfies whatever the vendor's schema asks of a field.

    Long enough for a minimum length, and obviously not a credential: a fixture
    holding something that looked like a real one is a fixture somebody
    eventually tries against a deployment.
    """
    if bool(getattr(field, "is_endpoint", False)):
        # An address, because that is what an address field is checked as. It
        # goes to the configuration tree rather than the vault, which is the one
        # half of this write that is meant to be readable afterwards.
        return "https://not-a-real-deployment.example.com"
    minimum = int(getattr(field, "min_length", 0) or 0)
    return "not-a-real-credential".ljust(max(minimum, 1), "x")
