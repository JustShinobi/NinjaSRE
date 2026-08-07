"""The real console, driven against the mock, on every screen and every scenario.

This is what the dataset is for, so it is what proves the dataset works. The
console is the real ``Console``, reaching the mock through its own transport and
its own client — nothing is stubbed between them — and the scenarios are the
committed ones.

Three of them matter for different reasons. ``populated`` proves the screens
render against a full deployment. ``empty`` is the only way an empty state gets
reviewed at all. ``degraded`` is the only way panel-level error handling is
exercised, because a panel's error state is not reachable when nothing fails.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from surfaces.console.app import Console
from surfaces.console.client import ConsoleClient, Response
from surfaces.console.session import sign_in
from tools.mockplane.server import MockPlane, build_mock, no_outbound_network

pytestmark = pytest.mark.contract

#: Every area the console renders. Named by path because that is what a person
#: types, and what a visual-regression run walks.
SCREENS: tuple[str, ...] = (
    "/",
    "/runs",
    "/runs/run-0001",
    "/runs/run-0003",
    "/interactions",
    "/memory",
    "/memory/topology",
    "/knowledge",
    "/config",
    "/config/org-northwind",
    "/catalogue",
    "/admin",
    "/onboarding",
)


@dataclass(frozen=True, slots=True)
class MockTransport:
    """The console's transport, wired straight into the mock."""

    mock: MockPlane

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        answer = self.mock.answer(method, path, body=body)
        text = answer.body.decode()
        import json

        try:
            document = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            document = {}
        return Response(
            status=answer.status,
            body=document if isinstance(document, dict) else {},
            text=text,
        )


async def console_for(scenario: str) -> tuple[Console, Any]:
    """Return the console and a signed-in session against ``scenario``."""
    mock = build_mock(scenario)
    console = Console(client=ConsoleClient(transport=MockTransport(mock)), api_base="mock://")
    principal = await console.client.principal()
    return console, sign_in("a-token", principal)


@pytest.mark.parametrize("scenario", ["populated", "empty", "degraded"])
@pytest.mark.parametrize("screen", SCREENS)
async def test_every_screen_renders(scenario: str, screen: str) -> None:
    console, session = await console_for(scenario)
    rendered = await console.render(screen, session)
    html = rendered.html()
    assert html, f"{screen} rendered nothing under {scenario}"
    assert "<html" in html.lower()


async def test_the_populated_scenario_puts_real_content_on_the_run_list() -> None:
    console, session = await console_for("populated")
    html = (await console.render("/runs", session)).html()
    assert "run-0001" in html


async def test_the_empty_scenario_renders_an_empty_state_rather_than_a_failure() -> None:
    console, session = await console_for("empty")
    html = (await console.render("/runs", session)).html()
    assert "run-0001" not in html
    assert "<html" in html.lower()


async def test_the_degraded_scenario_reaches_the_panel_level_error_handling() -> None:
    # ``/audit`` is under the administration area and the mock answers it 403,
    # which is one of the three cases the console has a different screen for.
    console, session = await console_for("degraded")
    rendered = await console.render("/admin", session)
    assert rendered.html(), "a failing panel took the whole page down"


async def test_a_viewer_sees_the_same_deployment_and_fewer_actions() -> None:
    owner_console, owner_session = await console_for("populated")
    viewer_console, viewer_session = await console_for("restricted")

    owner = (await owner_console.render("/runs", owner_session)).html()
    viewer = (await viewer_console.render("/runs", viewer_session)).html()

    assert "run-0001" in owner and "run-0001" in viewer, "the data changed with the role"
    assert owner != viewer, "the role made no difference to what is offered"


async def test_the_console_reaches_nothing_outside_the_process() -> None:
    with no_outbound_network():
        console, session = await console_for("populated")
        assert (await console.render("/runs", session)).html()


async def test_serving_one_scenario_twice_renders_the_same_page() -> None:
    first_console, first_session = await console_for("populated")
    second_console, second_session = await console_for("populated")
    assert (await first_console.render("/runs", first_session)).html() == (
        await second_console.render("/runs", second_session)
    ).html()


async def test_a_write_made_through_the_console_client_is_visible_on_the_next_read() -> None:
    console, _ = await console_for("populated")
    before = await console.client.runs()
    await console.client.start_investigation("look at the volume")
    after = await console.client.runs()
    assert len(after) == len(before) + 1
