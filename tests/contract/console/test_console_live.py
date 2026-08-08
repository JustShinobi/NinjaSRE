"""What the console's live layer claims about the deployment, held against it.

The live layer is the half of the console that cannot be proved by reading it.
Its whole value is a property — every event exactly once, in order, across a
reconnection — and the property is only worth anything if the console and the
deployment agree about the vocabulary it is carried in: the separator in a
cursor, the bound on reconnection, which event closes a card, and which events
mean a run has stopped.

None of those agreements can be asserted in TypeScript, because one side of each
of them is Python. They are asserted here.

The second half is the map from each success criterion to the named test that
proves it. A proof that is deleted or renamed fails here rather than quietly
ceasing to cover anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from config.constants.console import (
    CONSOLE_LIVE_BURST_BUDGET_MS,
    CONSOLE_LIVE_BURST_EVENTS,
)
from gateway.http.security.gateway_routes import GATEWAY_ROUTES
from platform.runs.cursor import Cursor
from platform.runs.events import TraceEventKind
from surfaces.console.live import CLOSING_KIND, OPENING_KIND
from surfaces.console.stream import MAX_RECONNECTIONS
from tools.console_toolchain import console_root

pytestmark = pytest.mark.contract

#: Where the console keeps the cursor arithmetic, the transport and the reducer.
LIVE_DIR: Final = console_root() / "src" / "live"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _constant(source: str, name: str) -> str:
    """Return the literal of ``export const NAME = <literal>;``."""
    found = re.search(rf"export const {name} = ('([^']*)'|[0-9]+);", source)
    assert found is not None, f"{name} is not declared"
    return found.group(2) if found.group(2) is not None else found.group(1)


def _string_list(source: str, name: str) -> tuple[str, ...]:
    """Return the string literals of a declared list, ``as const`` or typed."""
    found = re.search(rf"export const {name}[^=]*= \[(.*?)\];", source, re.DOTALL)
    assert found is not None, f"{name} is not declared"
    return tuple(re.findall(r"'([^']+)'", found.group(1)))


# --- The vocabulary the two halves have to agree about ------------------------------


def test_the_console_spells_a_cursor_the_way_the_deployment_does() -> None:
    """One separator, in two languages.

    Two spellings of one cursor is a reconnection that starts the transcript
    again from the beginning — and looks, from the outside, exactly like one
    that worked.
    """
    separator = _constant(_source(LIVE_DIR / "cursor.ts"), "CURSOR_SEPARATOR")

    wire = str(Cursor(run_id="run-0003", position=7))

    assert wire == f"run-0003{separator}7"


def test_the_console_gives_up_after_the_same_number_of_attempts_as_the_deployment() -> None:
    """The bound is a claim about behaviour, so it is one number rather than two."""
    declared = _constant(_source(LIVE_DIR / "connection.ts"), "MAX_RECONNECTIONS")

    assert int(declared) == MAX_RECONNECTIONS


def test_the_backoff_is_bounded_and_rises() -> None:
    """A backoff with no ceiling notices a deployment coming back half an hour late."""
    source = _source(LIVE_DIR / "connection.ts")
    found = re.search(r"export const BACKOFF_MS[^=]*= \[([^\]]*)\]", source)
    assert found is not None, "the console declares no backoff"
    waits = [int(value) for value in re.findall(r"\d+", found.group(1))]

    assert waits == sorted(waits), "a backoff that does not rise is a retry loop"
    assert waits[0] > 0, "an immediate first retry is not a backoff"
    assert len(waits) >= 2


def test_the_console_closes_a_card_on_the_kind_the_first_wave_established() -> None:
    """The mapping this feature had to preserve, held to the module that proved it.

    ``live.py`` established which event closes an interaction and which opens
    one, and tested it at that seam. This feature is the browser-side runtime
    for that mapping; a runtime that decided for itself which kind meant what
    would be a second opinion about the deployment's own vocabulary.
    """
    source = _source(LIVE_DIR / "reducer.ts")

    assert _constant(source, "CLOSING_KIND") == CLOSING_KIND
    assert _constant(source, "OPENING_KIND") == OPENING_KIND


@pytest.mark.parametrize("kind", [TraceEventKind.RUN_FINISHED, TraceEventKind.RUN_INTERRUPTED])
def test_every_kind_that_ends_a_run_ends_the_live_view(kind: TraceEventKind) -> None:
    """A terminal event the console does not know keeps a finished run "live" for ever."""
    terminal = _string_list(_source(LIVE_DIR / "reducer.ts"), "TERMINAL_KINDS")

    assert kind.value in terminal


def test_the_console_names_the_stream_route_the_gateway_serves() -> None:
    """The courier's address is the deployment's, spelled once."""
    source = _source(console_root() / "src" / "app" / "api" / "stream" / "[runId]" / "route.ts")

    assert "/v1/investigations/" in source
    assert "/stream" in source
    assert any(
        route.path == "/v1/investigations/{run_id}/stream" and route.method == "GET"
        for route in GATEWAY_ROUTES
    )


@pytest.mark.parametrize("action", ["cancel", "take-over", "resume", "messages"])
def test_every_run_action_the_console_posts_is_one_the_gateway_declares(action: str) -> None:
    """A control that posts to a route nothing serves is a control that always fails."""
    source = _source(console_root() / "src" / "app" / "api" / "run" / "route.ts")
    assert f"'{action}'" in source or f": '{action}'" in source

    declared = {(route.method, route.path) for route in GATEWAY_ROUTES}
    assert ("POST", f"/v1/investigations/{{run_id}}/{action}") in declared


def test_the_burst_budget_is_read_from_this_tier_rather_than_restated() -> None:
    """The number the console measures itself against is the one declared here."""
    source = _source(console_root() / "tests" / "unit" / "live" / "live-run.test.tsx")

    assert "CONSOLE_LIVE_BURST_EVENTS" in source
    assert "CONSOLE_LIVE_BURST_BUDGET_MS" in source
    # Declared rather than a magic number: a burst nobody sized is a budget
    # nobody can argue with.
    assert CONSOLE_LIVE_BURST_EVENTS >= 10_000
    assert CONSOLE_LIVE_BURST_BUDGET_MS > 0


# --- The structural claims easiest to lose in a rewrite -----------------------------


def _console_sources() -> tuple[Path, ...]:
    root = console_root() / "src"
    return tuple(
        path
        for path in sorted(root.rglob("*.ts*"))
        if path.name != "schema.ts" and "node_modules" not in path.parts
    )


def test_nothing_polls_for_data() -> None:
    """A polling loop is the thing a stream exists to make unnecessary.

    It is also the thing that survives a screen being closed, because an
    interval belongs to the page rather than to the component that started it.

    Exactly one interval exists in this console and it reads no data: the wall
    clock behind relative timestamps, which ticks so that "4m ago" becomes "5m
    ago" without a request. It is named here rather than excluded by a pattern,
    so a second one has to be argued for in this file.
    """
    intervals = {
        path.relative_to(console_root())
        for path in _console_sources()
        if "setInterval" in _source(path)
    }

    assert intervals == {Path("src/shell/browser.ts")}, (
        f"these poll rather than subscribe: {sorted(intervals)}"
    )
    clock = _source(console_root() / "src" / "shell" / "browser.ts")
    assert "fetch(" not in clock, "the one interval in this console reads data"


def test_the_live_view_and_the_replayed_view_are_still_one_component() -> None:
    """The claim the previous wave proved, and this one had to leave standing.

    The live layer draws through the same `Transcript`, and the two readers meet
    at one function. A live view that grew its own entry component is the
    divergence this rule exists to prevent, and it always drifts in the
    direction of the recorded account showing less.
    """
    drawing = [
        path.relative_to(console_root())
        for path in _console_sources()
        if 'data-testid="transcript-event"' in _source(path)
    ]

    assert drawing == [Path("src/surfaces/transcript-view.tsx")]
    assert "eventFromStream" in _source(console_root() / "src" / "live" / "reducer.ts"), (
        "the reducer builds transcript events itself rather than through the one mapping"
    )


def test_the_stream_courier_decides_nothing() -> None:
    """It adds a credential and a header, and pipes bytes. Nothing else."""
    source = _source(console_root() / "src" / "app" / "api" / "stream" / "[runId]" / "route.ts")

    assert "last-event-id" in source, "the cursor never reaches the deployment"
    for forbidden in ("sequence", "JSON.parse", "sort("):
        assert forbidden not in source, (
            f"the courier looks at {forbidden!r}; it is a courier, not a reader"
        )


# --- Each success criterion, against the test that proves it ------------------------


@dataclass(frozen=True, slots=True)
class Claim:
    """One thing this feature claims, and the named test that holds it."""

    criterion: str
    claim: str
    #: Relative to ``console/``.
    module: str
    #: A fragment of the test's own name, so a rename fails here.
    test: str


CLAIMS: Final[tuple[Claim, ...]] = (
    Claim(
        "SC-001",
        "a source that raises mid-flight delivers every sequence exactly once, in order",
        "tests/unit/live/reducer.test.ts",
        "delivers every sequence exactly once, in order, across a connection error",
    ),
    Claim(
        "SC-001",
        "and the reconnection presents the cursor it actually reached",
        "tests/unit/live/connection.test.ts",
        "presents nothing on a first connection and the cursor on every one after",
    ),
    Claim(
        "SC-002",
        "a replaying source after reconnection is de-duplicated",
        "tests/unit/live/reducer.test.ts",
        "discards an event it has already applied",
    ),
    Claim(
        "SC-002",
        "and an out-of-order burst is ordered before any of it is shown",
        "tests/unit/live/reducer.test.ts",
        "orders an out-of-order burst before exposing any of it",
    ),
    Claim(
        "SC-003",
        "a decision arriving as a run event closes the card and names the decider",
        "tests/unit/live/reducer.test.ts",
        "closes the card and names who decided it and where",
    ),
    Claim(
        "SC-003",
        "and the closed item leaves the notification centre without a refresh",
        "tests/unit/live/live-run.test.tsx",
        "publishes an interaction decided elsewhere",
    ),
    Claim(
        "SC-004",
        "an optimistic write refused by the server reverts and states why",
        "tests/unit/live/store.test.ts",
        "reverts to what was there and states the deployment",
    ),
    Claim(
        "SC-004",
        "and a control on a screen does the same against a real refusal",
        "tests/unit/live/live-run.test.tsx",
        "reverts to not having control when the deployment refuses",
    ),
    Claim(
        "SC-005",
        "ten thousand events apply inside the declared budget",
        "tests/unit/live/live-run.test.tsx",
        "applies ten thousand events, exactly once each, inside the declared budget",
    ),
    Claim(
        "SC-006",
        "no subscription outlives its screen, across repeated mount and unmount",
        "tests/unit/live/connection.test.ts",
        "opens and closes the same number of times over a hundred mount cycles",
    ),
    Claim(
        "SC-006",
        "and the last screen watching a run is what closes its stream",
        "tests/unit/live/store.test.ts",
        "closes it when the last screen watching it goes",
    ),
    Claim(
        "SC-007",
        "a browser drives a live run against a real gateway",
        "tests/e2e/live.spec.ts",
        "a run that is still going is watched rather than read back",
    ),
    Claim(
        "FR-005",
        "a disconnected stream never presents itself as live",
        "tests/unit/live/live-run.test.tsx",
        "never presents a stream it has given up on as live",
    ),
    Claim(
        "FR-007",
        "a token expiring mid-stream ends the session through the one collapse path",
        "tests/unit/live/connection.test.ts",
        "ends the session through the one collapse path",
    ),
    Claim(
        "FR-018",
        "a live list does not reorder under the operator's pointer",
        "tests/unit/live/store.test.ts",
        "updates a row in place rather than moving it under the pointer",
    ),
    Claim(
        "FR-019",
        "the notification count and the notification list cannot disagree",
        "tests/unit/live/store.test.ts",
        "cannot disagree, because the count is the length of the one list",
    ),
    Claim(
        "NFR-002",
        "a background tab does no work and recovers fully on return",
        "tests/unit/live/connection.test.ts",
        "does no work while the tab is in the background",
    ),
)


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: f"{claim.criterion}: {claim.claim}")
def test_each_success_criterion_is_proven_by_a_named_test(claim: Claim) -> None:
    """The proof exists, in the file it is supposed to be in, under that name."""
    module = console_root() / claim.module
    assert module.is_file(), f"{claim.criterion} names {claim.module}, which is not there"
    assert claim.test in _source(module), (
        f"{claim.criterion} ({claim.claim}) names a test containing {claim.test!r} in "
        f"{claim.module}, and there is none"
    )


def test_every_criterion_the_specification_declares_is_claimed() -> None:
    """Seven criteria, none of them quietly dropped from the list above."""
    declared = {claim.criterion for claim in CLAIMS if claim.criterion.startswith("SC-")}
    assert declared == {f"SC-{number:03d}" for number in range(1, 8)}
