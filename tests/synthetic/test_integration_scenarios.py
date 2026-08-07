"""The seventh artefact, run: every integration exercised end to end.

Parameterised over the catalogue, like everything else in this framework, so an
integration added tomorrow is covered by this file without being mentioned in
it. What each run drives is the whole path — the registered capability, the
vendor client, the credential proxy, the injection rule, and a scripted vendor —
with nothing mocked in between.

That is what makes this the artefact that stops an integration rotting. A
renamed response field, a changed pagination cursor, an injection that no longer
matches the schema: none of those raise anywhere else in the suite, because
every other test either checks the declaration or checks the client against a
double of its own making. Here the tool's own output has to come out right after
crossing every layer that could have quietly dropped it.
"""

from __future__ import annotations

import importlib

import pytest

from integrations._catalogue.discovery import catalogue
from tests.synthetic.integration_scenarios import (
    IntegrationScenario,
    capability_named,
    run_scenario,
)

pytestmark = pytest.mark.synthetic

CATALOGUE = catalogue()
ENTRIES = {entry.name: entry for entry in CATALOGUE}


def scenarios_of(integration: str) -> tuple[IntegrationScenario, ...]:
    """Return the scenarios ``integration``'s module declares."""
    module = importlib.import_module(f"tests.synthetic.integration_scenarios.{integration}")
    declared = getattr(module, "SCENARIOS", ())
    return tuple(declared)


ALL_SCENARIOS: tuple[IntegrationScenario, ...] = tuple(
    scenario for entry in CATALOGUE for scenario in scenarios_of(entry.name)
)


def test_every_catalogued_integration_declares_at_least_one_scenario() -> None:
    """The parity check asserts the file exists; this asserts it says something."""
    empty = [entry.name for entry in CATALOGUE if not scenarios_of(entry.name)]

    assert not empty, f"no synthetic scenario exercises {', '.join(empty)}"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda scenario: scenario.key)
async def test_the_scenario_reaches_the_vendor_and_produces_its_finding(
    scenario: IntegrationScenario,
) -> None:
    entry = ENTRIES[scenario.integration]
    tool = capability_named(scenario.capability, _declared(scenario.integration))

    outcome = await run_scenario(scenario, descriptor=entry.descriptor, tool=tool)

    assert outcome.result.succeeded, _why(outcome.result)
    assert outcome.result.evidence, "a capability that produced no evidence produced a claim"
    assert scenario.expected_summary in outcome.result.evidence[0].summary
    assert outcome.result.truncated is scenario.expected_truncated


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda scenario: scenario.key)
async def test_the_scenario_routes_every_call_through_the_proxy(
    scenario: IntegrationScenario,
) -> None:
    """Article IV, exercised rather than declared: the vendor sees what the proxy added."""
    entry = ENTRIES[scenario.integration]
    tool = capability_named(scenario.capability, _declared(scenario.integration))

    outcome = await run_scenario(scenario, descriptor=entry.descriptor, tool=tool)

    assert outcome.vendor.sent, f"{scenario.key}: nothing reached the vendor at all"
    for request in outcome.vendor.sent:
        assert entry.descriptor.rule.permits(request.host)
    for expected in scenario.expected_paths:
        assert any(expected in request.url for request in outcome.vendor.sent), (
            f"{scenario.key}: no call reached {expected}"
        )


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda scenario: scenario.key)
async def test_no_credential_value_appears_in_what_the_scenario_produced(
    scenario: IntegrationScenario,
) -> None:
    """The result goes into a trace, and a trace is read by people and models."""
    entry = ENTRIES[scenario.integration]
    tool = capability_named(scenario.capability, _declared(scenario.integration))

    outcome = await run_scenario(scenario, descriptor=entry.descriptor, tool=tool)

    rendered = repr(outcome.result)
    for name in entry.descriptor.schema.secret_names:
        value = scenario.credential.get(name)
        if value:
            assert value not in rendered, f"{scenario.key}: {name} reached the result"


async def test_a_capability_whose_integration_is_unbound_says_so_rather_than_returning_nothing() -> (
    None
):
    """An empty answer would teach the investigation something about the estate."""
    from integrations._base.access import clear, current, restore

    scenario = ALL_SCENARIOS[0]
    tool = capability_named(scenario.capability, _declared(scenario.integration))
    previous = current()
    clear()
    try:
        result = await tool.invoke(dict(scenario.arguments))
    finally:
        restore(previous)

    assert not result.succeeded
    assert result.error is not None
    assert scenario.integration in result.error.message
    assert "not configured" in result.error.message


def _declared(integration: str) -> tuple[object, ...]:
    """Return every attribute the integration's tools package binds."""
    module = importlib.import_module(f"integrations.{integration}.tools")
    return tuple(vars(module).values())


def _why(result: object) -> str:
    """Return the failure message, for an assertion that would otherwise say False."""
    error = getattr(result, "error", None)
    return str(error) if error is not None else "no error attached"
