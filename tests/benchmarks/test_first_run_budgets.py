"""SC-010. Bring-up, demo population and the self-check each meet their budget.

Two of the three are measured here against real work. The third — bring-up to a
signed-in console — is a wall-clock claim about a machine pulling container
images, so what is asserted here is the *shape* of it: the declared budget equals
the sum of the shipped plan's steps up to and including signing in, so a step
added later cannot quietly push it out without somebody noticing the number no
longer adds up.

That is the same split ``tools/measure_first_investigation.py`` already makes for
the fifteen-minute claim, and for the same reason: the leg that depends on
somebody else's network is measured on a real machine, and the leg this
repository controls is held to a number in the gate.
"""

from __future__ import annotations

import time

import pytest

from config.constants.first_run import (
    BRING_UP_TO_SIGN_IN_BUDGET_SECONDS,
    DEMO_POPULATION_BUDGET_SECONDS,
    SELF_CHECK_BUDGET_SECONDS,
    SELF_CHECK_TIMEOUT_SECONDS,
)
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.startup.bootstrap import bring_up
from platform.startup.demo import load_dataset, seed_demonstration
from platform.startup.profiles import DeploymentProfile
from platform.startup.selfcheck import self_check
from platform.startup.setup import first_run_plan

pytestmark = pytest.mark.benchmark


# --- NFR-001: bring-up to a signed-in console -----------------------------------


def test_the_declared_bring_up_budget_is_what_the_shipped_plan_actually_costs() -> None:
    """The number and the plan cannot drift, because one is derived from the other."""
    plan = first_run_plan(DeploymentProfile.STANDARD)
    names = [step.name for step in plan.steps]
    through_sign_in = names.index("sign in") + 1
    planned = sum(step.budget_seconds for step in plan.steps[:through_sign_in])

    assert planned == BRING_UP_TO_SIGN_IN_BUDGET_SECONDS, (
        f"the standard plan now costs {planned}s to a signed-in console and the declared "
        f"budget is {BRING_UP_TO_SIGN_IN_BUDGET_SECONDS}s. A step was added without "
        f"revisiting the budget."
    )


def test_bring_up_to_a_signed_in_console_fits_inside_the_first_investigation_budget() -> None:
    """NFR-001 against the fifteen minutes SC-001 allows for the whole path."""
    plan = first_run_plan(DeploymentProfile.STANDARD)

    assert plan.budget_seconds > BRING_UP_TO_SIGN_IN_BUDGET_SECONDS
    assert plan.within_budget


async def test_the_part_of_bring_up_this_repository_controls_is_immediate() -> None:
    """Everything bring-up itself does — the organisation, the principal, the
    grant, the credential, the file — happens while the operator is still
    reading the previous line."""
    store = FakePersistence()
    tokens = TokenService(gateway=store)

    started = time.perf_counter()
    await bring_up(store, tokens, environ={"NINJASRE_STATE_DIR": _scratch()})
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"bring-up's own work took {elapsed:.2f}s"


# --- NFR-002: demo population ------------------------------------------------------


async def test_the_demonstration_populates_inside_its_budget() -> None:
    """NFR-002, measured against the whole committed dataset."""
    store = FakePersistence()
    dataset = load_dataset()

    started = time.perf_counter()
    report = await seed_demonstration(store, dataset=dataset)
    elapsed = time.perf_counter() - started

    assert report.total > 100, "the budget was met by loading almost nothing"
    assert elapsed < DEMO_POPULATION_BUDGET_SECONDS, (
        f"populating {report.total} records took {elapsed:.1f}s, over the "
        f"{DEMO_POPULATION_BUDGET_SECONDS}s budget"
    )


# --- NFR-003: the self-check ----------------------------------------------------------


async def test_the_self_check_completes_inside_its_budget() -> None:
    store = FakePersistence()

    started = time.perf_counter()
    report = await self_check(store)
    elapsed = time.perf_counter() - started

    assert elapsed < SELF_CHECK_BUDGET_SECONDS
    assert report.duration_seconds < SELF_CHECK_BUDGET_SECONDS


async def test_the_self_check_does_not_hang_on_a_dependency_that_never_answers() -> None:
    """NFR-003's second half, measured rather than asserted structurally.

    Every collaborator absent and a store that is closed: the worst case this
    deployment can produce, and it still comes back inside one timeout's worth
    of headroom rather than nine.
    """
    store = FakePersistence()
    await store.close()

    started = time.perf_counter()
    await self_check(store, timeout_seconds=SELF_CHECK_TIMEOUT_SECONDS)
    elapsed = time.perf_counter() - started

    assert elapsed < SELF_CHECK_TIMEOUT_SECONDS * 2, (
        f"the worst-case self-check took {elapsed:.1f}s, which means the checks are "
        f"running one after another rather than together"
    )


def _scratch() -> str:
    """Return a directory this measurement may write its credential file into."""
    import tempfile

    return tempfile.mkdtemp(prefix="ninjasre-bringup-budget-")
