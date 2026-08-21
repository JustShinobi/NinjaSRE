"""Verifying that a configured model can do the two things an investigation needs.

An endpoint answering is not the property that matters. What matters is whether
the model can call a tool and return structured output, because a model that
cannot will fail in the middle of the first investigation with something
inscrutable — and the operator will conclude the platform is broken rather than
that the model they pointed it at is a completion model.
"""

from __future__ import annotations

import pytest

from core.llm.preflight import CheckResult, CheckStatus, PreflightReport
from core.llm.verification import ModelVerdict, contract_verdict, verify_model

pytestmark = pytest.mark.unit


def _report(**statuses: CheckStatus) -> PreflightReport:
    """Return a preflight report with the named checks at the given statuses."""
    defaults: dict[str, CheckStatus] = {
        "credentials": CheckStatus.PASSED,
        "authentication": CheckStatus.PASSED,
        "tool calling": CheckStatus.PASSED,
        "structured output": CheckStatus.PASSED,
        "streaming": CheckStatus.PASSED,
    }
    defaults.update({name.replace("_", " "): value for name, value in statuses.items()})
    return PreflightReport(
        provider_id="local",
        model_id="tiny-1b",
        transport="openai_compat",
        checks=tuple(CheckResult(name, status) for name, status in defaults.items()),
    )


# --- The failure the whole check exists for -------------------------------------


def test_an_endpoint_that_answers_but_cannot_tool_call_fails_verification() -> None:
    """T-015, SC-006. Degraded is a pass for preflight and a failure here, and
    that difference is the point: preflight describes, verification decides."""
    verdict = contract_verdict(_report(tool_calling=CheckStatus.DEGRADED))

    assert verdict.satisfied is False


def test_the_message_names_the_actual_limitation_rather_than_a_bare_failure() -> None:
    verdict = contract_verdict(_report(tool_calling=CheckStatus.DEGRADED))

    assert "tool" in verdict.limitation.lower()
    assert "tiny-1b" in verdict.limitation
    # Not "verification failed", not "connection error": the sentence says what
    # the endpoint did and what it could not do.
    assert verdict.limitation != "verification failed"
    assert verdict.remedy


def test_an_endpoint_that_cannot_return_structured_output_fails_the_same_way() -> None:
    verdict = contract_verdict(_report(structured_output=CheckStatus.FAILED))

    assert verdict.satisfied is False
    assert "structured" in verdict.limitation.lower()
    assert verdict.remedy


def test_structured_output_reached_by_a_fallback_is_reported_and_still_accepted() -> None:
    """A model that gets there through a prompt-and-parse shim does satisfy the
    contract — degraded natively, working in practice. Saying so is honest; and
    refusing it would rule out most self-hosted models, which is feature 043's
    whole subject."""
    verdict = contract_verdict(
        _report(structured_output=CheckStatus.DEGRADED, tool_calling=CheckStatus.PASSED)
    )

    assert verdict.satisfied is True
    assert "degraded" in verdict.summary_line.lower() or "fallback" in verdict.summary_line.lower()


def test_a_credential_that_does_not_resolve_is_named_before_anything_else() -> None:
    verdict = contract_verdict(_report(credentials=CheckStatus.FAILED))

    assert verdict.satisfied is False
    assert "credential" in verdict.limitation.lower()


def test_an_endpoint_that_does_not_authenticate_is_not_a_tool_calling_problem() -> None:
    """The two are confused constantly, and the remedies have nothing in common."""
    verdict = contract_verdict(
        _report(authentication=CheckStatus.FAILED, tool_calling=CheckStatus.DEGRADED)
    )

    assert "authenticat" in verdict.limitation.lower()


def test_a_model_that_does_everything_satisfies_the_contract() -> None:
    verdict = contract_verdict(_report())

    assert verdict.satisfied is True
    assert verdict.limitation == ""
    assert verdict.remedy == ""
    assert "tiny-1b" in verdict.summary_line


# --- Naming what would work ------------------------------------------------------


def test_the_models_that_do_satisfy_the_contract_are_named_where_they_are_known() -> None:
    """T-017. "Here are the ones it offers that do" is the sentence the spec asks
    for, and it is only useful if it lists models rather than saying there may
    be some."""
    verdict = contract_verdict(
        _report(tool_calling=CheckStatus.DEGRADED),
        alternatives=("qwen2.5-coder:14b", "llama3.1:70b"),
    )

    assert verdict.alternatives == ("qwen2.5-coder:14b", "llama3.1:70b")
    assert "qwen2.5-coder:14b" in verdict.remedy


def test_an_endpoint_that_cannot_enumerate_its_models_says_so_rather_than_guessing() -> None:
    verdict = contract_verdict(_report(tool_calling=CheckStatus.DEGRADED), alternatives=())

    assert verdict.alternatives == ()
    assert "qwen" not in verdict.remedy
    assert verdict.remedy


def test_a_satisfied_verdict_does_not_advertise_alternatives() -> None:
    verdict = contract_verdict(_report(), alternatives=("something-else",))

    assert verdict.remedy == ""


# --- Driving the real preflight ---------------------------------------------------


async def test_verification_exercises_tool_calling_and_structured_output() -> None:
    """T-016. The verdict comes from the probes, not from a capability flag."""
    called: list[str] = []

    async def fake_preflight() -> PreflightReport:
        called.append("preflight")
        return _report()

    verdict = await verify_model(run_preflight=fake_preflight)

    assert called == ["preflight"]
    assert verdict.satisfied is True


async def test_verification_asks_the_endpoint_what_else_it_offers_when_it_fails() -> None:
    async def fake_preflight() -> PreflightReport:
        return _report(tool_calling=CheckStatus.DEGRADED)

    async def enumerate_models() -> tuple[str, ...]:
        return ("tiny-1b", "qwen2.5:32b")

    verdict = await verify_model(run_preflight=fake_preflight, list_models=enumerate_models)

    # The model that just failed is not offered back as its own alternative.
    assert verdict.alternatives == ("qwen2.5:32b",)


async def test_an_endpoint_that_refuses_to_enumerate_does_not_fail_verification() -> None:
    """Listing models is a nicety. An endpoint that will not is still verifiable."""

    async def fake_preflight() -> PreflightReport:
        return _report(tool_calling=CheckStatus.DEGRADED)

    async def enumerate_models() -> tuple[str, ...]:
        raise ConnectionError("no /models on this endpoint")

    verdict = await verify_model(run_preflight=fake_preflight, list_models=enumerate_models)

    assert verdict.satisfied is False
    assert verdict.alternatives == ()
    assert verdict.remedy


def test_a_verdict_round_trips_through_its_record() -> None:
    verdict = ModelVerdict(
        provider_id="local",
        model_id="tiny-1b",
        satisfied=False,
        limitation="it does not call tools",
        remedy="pick another model",
        alternatives=("big-1",),
    )

    record = verdict.to_record()

    assert record["satisfied"] is False
    assert record["alternatives"] == ["big-1"]
