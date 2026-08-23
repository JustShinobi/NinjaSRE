"""The path that serves an investigation is the path that composes the recorder.

A mechanism only a test constructs is not shipped. This walks the actual
composition roots — the ones the deployment's own boot sequence calls — and
proves each one leaves the runner it built with somewhere to write, and that
rebuilding the runner after configuration is read does not lose it.
"""

from __future__ import annotations

import pytest

from gateway.http.asgi import UnconfiguredInvestigator, investigator_of
from gateway.http.runtime import recompose_investigator
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.architecture

_NAMES_A_FACTORY = {"NINJASRE_INVESTIGATOR": "gateway.runtime.factory:build_investigator"}
_NAMES_NONE = {"NINJASRE_INVESTIGATOR": ""}


def test_investigator_of_attaches_somewhere_to_write_when_given_a_store() -> None:
    """The single attach point named in the plan: ``investigator_of``."""
    runner = investigator_of(
        _NAMES_A_FACTORY,
        store=FakePersistence(),
        guardrails=GuardrailEngine(),
        broker=RunEventBroker(),
    )

    assert isinstance(runner, ReActInvestigationRunner)
    assert runner.can_record, "a runner investigator_of attached a store to must know it can record"


def test_a_deployment_naming_no_investigator_still_has_no_recorder_and_no_error() -> None:
    """Nothing named, still comes up, and it is honestly composed-nothing."""
    runner = investigator_of(
        _NAMES_NONE, store=FakePersistence(), guardrails=GuardrailEngine(), broker=RunEventBroker()
    )

    assert isinstance(runner, UnconfiguredInvestigator)


def test_recomposition_preserves_the_attached_recorder() -> None:
    """Rebuilding the investigator after configuration is read must not lose it.

    This is the seam ``gateway/http/runtime.py``'s own module docstring names:
    a runner composed first and then quietly rebuilt without a store would
    write for a while and then, silently, stop.
    """
    store = FakePersistence()
    state = GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=investigator_of(
            _NAMES_A_FACTORY, store=store, guardrails=GuardrailEngine(), broker=RunEventBroker()
        ),
    )
    assert isinstance(state.investigator, ReActInvestigationRunner)
    assert state.investigator.can_record

    recompose_investigator(state, environ=_NAMES_A_FACTORY)

    assert isinstance(state.investigator, ReActInvestigationRunner)
    assert state.investigator.can_record, (
        "recompose_investigator rebuilt the runner without re-attaching a store to write to"
    )


def test_recomposition_of_an_unconfigured_deployment_stays_unconfigured() -> None:
    store = FakePersistence()
    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=UnconfiguredInvestigator()
    )

    recompose_investigator(state, environ=_NAMES_A_FACTORY)

    assert isinstance(state.investigator, UnconfiguredInvestigator), (
        "a deployment that named no runtime at boot must not gain one silently later"
    )
