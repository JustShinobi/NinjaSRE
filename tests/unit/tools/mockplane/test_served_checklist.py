"""What the mocked setup checklist says about the runtime nobody composed.

``platform.startup.checklist.build_checklist`` grew a fifth step — whether this
process actually holds something that can drive an investigation — and the
mock this tooling serves has to say the same thing, or a screen tested against
it is a screen tested against a document nothing serves. This is exactly the
property ``checklist_record``'s own docstring already claims and the point
these tests hold it to.
"""

from __future__ import annotations

from typing import cast

from config.constants.first_run import (
    SETUP_READINESS_VERIFIED,
    SETUP_STATE_BLOCKED,
    SETUP_STATE_DONE,
    SETUP_STATE_READY,
    SETUP_STEP_FIRST_INVESTIGATION,
    SETUP_STEP_INVESTIGATION_RUNTIME,
)
from tools.mockplane.dataset.served import checklist_record, setup_records


def _step(body: dict[str, object], name: str) -> dict[str, object]:
    """Return the step named ``name``, failing with a readable message if absent."""
    steps = body["steps"]
    assert isinstance(steps, list)
    for entry in steps:
        assert isinstance(entry, dict)
        if entry.get("name") == name:
            return cast(dict[str, object], entry)
    raise AssertionError(f"no {name!r} step among {steps!r}")


def test_the_runtime_step_exists_and_names_no_setting() -> None:
    body = checklist_record(source=True).body
    runtime = _step(body, SETUP_STEP_INVESTIGATION_RUNTIME)

    assert runtime["state"] == SETUP_STATE_READY
    for field in ("detail", "action"):
        assert "NINJASRE_INVESTIGATOR" not in str(runtime[field])


def test_the_runtime_step_is_blocked_until_an_infrastructure_source_is_connected() -> None:
    body = checklist_record(source=False).body
    runtime = _step(body, SETUP_STEP_INVESTIGATION_RUNTIME)

    assert runtime["state"] == SETUP_STATE_BLOCKED


def test_the_runtime_step_is_done_once_the_deployment_says_it_composed_one() -> None:
    body = checklist_record(source=True, runtime=True).body
    runtime = _step(body, SETUP_STEP_INVESTIGATION_RUNTIME)

    assert runtime["state"] == SETUP_STATE_DONE


def test_the_first_investigation_step_waits_on_the_runtime_not_only_the_source() -> None:
    # An estate connected but no runtime composed: the real backend blocks
    # "run your first investigation" on the runtime step, not the source step
    # directly, because nothing can drive one without it either way.
    body = checklist_record(source=True, runtime=False).body
    investigation = _step(body, SETUP_STEP_FIRST_INVESTIGATION)

    assert investigation["state"] == SETUP_STATE_BLOCKED


def test_a_finished_deployment_is_not_complete_while_nothing_can_investigate() -> None:
    body = checklist_record(
        provider=SETUP_READINESS_VERIFIED, source=True, investigated=True, runtime=False
    ).body

    assert body["complete"] is False


def test_the_fully_set_up_scenario_composes_a_runtime_so_it_stays_complete() -> None:
    # setup_records() is what the "populated" scenario is built from. A run
    # cannot have finished without something to run it, so the baseline this
    # scenario is built from has to say the runtime exists too — otherwise
    # every screen that reads "this deployment is fully set up" from it would
    # have been reading a document that contradicts its own investigated flag.
    (checklist,) = (record for record in setup_records() if record.slug == "setup-checklist")

    assert checklist.body["complete"] is True
    runtime = _step(checklist.body, SETUP_STEP_INVESTIGATION_RUNTIME)
    assert runtime["state"] == SETUP_STATE_DONE
