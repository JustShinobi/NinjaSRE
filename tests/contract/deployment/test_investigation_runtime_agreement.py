"""Three surfaces answer "can this deployment investigate?", and they agree.

The checklist step an operator reads during setup, the self-check a diagnosis
runs, and the route that actually starts an investigation each have to give the
same answer, because a deployment that says yes in one place and no in another
is worse than one that says no everywhere: it sends somebody to press a button
that was never going to work.

What makes the three agree is that none of them reads a setting. They all ask
what the composition root actually built. A check that read the environment
variable would answer yes for a variable naming a factory that fails to
import — and that specific shape, a deployment that looks configured and is
not, is what left two incidents unstarted with nothing on any screen to say
why.

The refusal is asserted for its content as well as its existence: it names what
is missing without naming a setting of the process, because the console renders
it and a deploy instruction on that screen is the thing the failure translation
exists to keep off it.
"""

from __future__ import annotations

import pytest

from gateway.http.asgi import (
    InvestigatorNotConfigured,
    UnconfiguredInvestigator,
    investigator_of,
)
from gateway.http.runtime import runtime_composed
from gateway.runtime.factory import build_investigator
from platform.startup.checklist import _runtime_step
from platform.startup.selfcheck import investigation_runtime_check
from tests.unit.gateway.http.conftest import Deployment, deployment  # noqa: F401

pytestmark = pytest.mark.contract

#: What the deployment reads to find a factory. Named here so this file can
#: assert the operator never meets it on a screen.
_SETTING = "NINJASRE_INVESTIGATOR"


async def _self_check_says_yes(state: object) -> bool:
    """Return the self-check's answer, run the way the diagnosis runs it."""
    check = investigation_runtime_check(lambda: runtime_composed(state))  # type: ignore[arg-type]
    outcome = await check.run()
    return outcome.findings == ()


async def test_a_composed_runtime_reads_as_present_on_every_surface(
    deployment: Deployment,  # noqa: F811
) -> None:
    """All three say yes, and the route starts rather than refusing."""
    deployment.state.investigator = build_investigator()

    assert runtime_composed(deployment.state) is True
    assert _runtime_step(runtime_composed(deployment.state), blocked=False).done is True
    assert await _self_check_says_yes(deployment.state) is True


async def test_with_nothing_composed_all_three_say_no_together(
    deployment: Deployment,  # noqa: F811
) -> None:
    """Asserted together rather than one at a time.

    Each on its own would pass against a deployment where only that surface
    had been taught to say no, which is the disagreement this file exists to
    rule out.
    """
    deployment.state.investigator = UnconfiguredInvestigator()

    assert runtime_composed(deployment.state) is False
    assert _runtime_step(runtime_composed(deployment.state), blocked=False).done is False
    assert await _self_check_says_yes(deployment.state) is False


async def test_a_factory_that_will_not_load_answers_no_and_never_yes(
    deployment: Deployment,  # noqa: F811
) -> None:
    """The question that a settings-reading check would get wrong.

    A reference is set, so anything reading configuration would report a
    runtime. Nothing loads, so there is none. The three surfaces read the
    composed object and say so.
    """
    deployment.state.investigator = investigator_of(
        {_SETTING: "a.module.that.is.not:there"},
        store=deployment.state.gateway,
        guardrails=deployment.state.guardrails,
        broker=deployment.state.broker,
    )

    assert runtime_composed(deployment.state) is False
    assert _runtime_step(runtime_composed(deployment.state), blocked=False).done is False
    assert await _self_check_says_yes(deployment.state) is False


async def test_starting_an_investigation_refuses_with_a_remedy_and_not_a_crash(
    deployment: Deployment,  # noqa: F811
) -> None:
    """A refusal an operator can act on, and not a server error.

    This is the one place the setting is allowed to be named, and it should
    be: the refusal is what the process records, and an operator reading a log
    needs the name of the thing to set. What may never carry it is a screen —
    the checklist step and the self-check both say what is missing in words
    instead, and their own tests hold them to that.
    """
    from gateway.http.services import InvestigationStart

    runner = UnconfiguredInvestigator()

    with pytest.raises(InvestigatorNotConfigured) as refusal:
        await runner.investigate(
            InvestigationStart(
                objective="diagnose cedar",
                run_id="run-1",
                team_node_id="team-platform",
                principal_id="responder-1",
            )
        )

    said = str(refusal.value)
    # Actionable: it names the setting and what to set it to, rather than
    # reporting that something went wrong.
    assert _SETTING in said
    assert "module:factory" in said


async def test_the_surfaces_are_reading_one_answer_rather_than_three(
    deployment: Deployment,  # noqa: F811
) -> None:
    """Flip the composed object once; every surface follows.

    This is what "they agree" means operationally — not that three
    independent implementations happen to match today, but that there is one
    answer and three readers of it.
    """
    for investigator, expected in (
        (build_investigator(), True),
        (UnconfiguredInvestigator(), False),
    ):
        deployment.state.investigator = investigator
        answers = {
            runtime_composed(deployment.state),
            _runtime_step(runtime_composed(deployment.state), blocked=False).done,
            await _self_check_says_yes(deployment.state),
        }
        assert answers == {expected}
