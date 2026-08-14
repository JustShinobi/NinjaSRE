"""The console walk that stands between a broken screen and a promotion.

Two shell routes answered 500 for every operator of an unconfigured deployment
and were promoted anyway, because the smoke checks all pointed at the API. The
walk exists so that the next broken screen fails a deploy instead of a Tuesday.

Everything here runs against a stub console on the loopback interface, started
per test on a port the kernel chooses. Nothing reads the clock, the filesystem
or a real deployment, so two runs of this file agree.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Final
from urllib.parse import parse_qs, urlparse

import pytest

from config.constants.console import CONSOLE_SESSION_COOKIE, CONSOLE_SESSION_ENDPOINT
from tools.console_smoke import EXIT_REFUSED, SHELL_PATHS, main, walk

#: The credential the stub hands out. Obviously not one: a fixture that looked
#: like a real token is a fixture somebody eventually tries in a deployment.
TOKEN: Final = "stub-console-session"

USERNAME: Final = "avery"
PASSWORD: Final = "correct horse"


@dataclass
class Console:
    """What the stub console does, so a test can make it misbehave."""

    #: Paths that answer something other than 200, and what they answer.
    broken: dict[str, int] = field(default_factory=dict)
    #: Whether the sign-in accepts anything at all.
    accepts: bool = True
    #: Every path that was asked for, in the order it was asked.
    visited: list[str] = field(default_factory=list)

    def breaks(self, *paths: str, status: int = 500) -> None:
        """Make each of ``paths`` answer ``status``, refusing one the walk skips.

        A path the walk never visits is not a broken route — it is a typo, or a
        route that was renamed out from under the test. The stub would answer
        nobody, the assertion would compare two empty things, and the test would
        keep passing while proving nothing. Setting ``broken`` directly is how
        two of these went on naming a route for the whole time after it was
        folded into another one.
        """
        unknown = [path for path in paths if path not in SHELL_PATHS]
        if unknown:
            raise AssertionError(
                f"{unknown} is not walked, so breaking it asserts nothing. "
                f"The walk visits {list(SHELL_PATHS)}"
            )
        self.broken.update(dict.fromkeys(paths, status))


def _handler(state: Console) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_: object) -> None:
            """Silence, so a failing test's output is the failure."""

        def _answer(self, status: int, body: bytes = b"", **headers: str) -> None:
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 — the base class spells it this way
            if urlparse(self.path).path != CONSOLE_SESSION_ENDPOINT:
                self._answer(404)
                return
            length = int(self.headers.get("content-length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            good = (
                state.accepts
                and form.get("username") == [USERNAME]
                and form.get("password") == [PASSWORD]
            )
            if not good:
                self._answer(303, location="/sign-in?reason=rejected")
                return
            self._answer(
                303,
                location="/",
                set_cookie=f"{CONSOLE_SESSION_COOKIE}={TOKEN}; Path=/; HttpOnly",
            )

        def do_GET(self) -> None:  # noqa: N802 — the base class spells it this way
            path = urlparse(self.path).path
            state.visited.append(path)
            if f"{CONSOLE_SESSION_COOKIE}={TOKEN}" not in self.headers.get("cookie", ""):
                # What the guard above the router does, which is the thing a
                # walk that forgot its credential would otherwise pass against.
                self._answer(307, location="/sign-in")
                return
            self._answer(state.broken.get(path, 200), b"<html></html>")

    return Handler


@pytest.fixture
def console() -> Iterator[tuple[Console, str]]:
    """A stub console, and the address it is listening on."""
    state = Console()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_walk_visits_every_shell_route_signed_in(console: tuple[Console, str]) -> None:
    state, base = console

    results = walk(base, USERNAME, PASSWORD)

    assert [result.path for result in results] == list(SHELL_PATHS)
    assert all(result.status == 200 for result in results), results
    # Signed in, rather than bounced to the form — which every route would have
    # answered 200 for if the walk followed redirects.
    assert state.visited == list(SHELL_PATHS)


def test_a_route_that_does_not_answer_200_is_named(console: tuple[Console, str]) -> None:
    state, base = console
    state.breaks("/integrations", "/autonomy")

    results = walk(base, USERNAME, PASSWORD)

    assert {result.path: result.status for result in results if result.status != 200} == {
        "/integrations": 500,
        "/autonomy": 500,
    }


def test_the_command_refuses_the_deploy_when_a_route_is_broken(
    console: tuple[Console, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    state, base = console
    state.breaks("/integrations")

    code = main(["--base-url", base, "--username", USERNAME, "--password", PASSWORD])

    assert code == 1
    printed = capsys.readouterr().out
    # Named, with its status, because "the console smoke failed" sends somebody
    # to read thirteen routes by hand.
    assert "/integrations" in printed
    assert "500" in printed


def test_the_command_passes_a_console_whose_routes_all_answer(
    console: tuple[Console, str],
) -> None:
    _, base = console

    assert main(["--base-url", base, "--username", USERNAME, "--password", PASSWORD]) == 0


def test_a_refused_sign_in_is_told_apart_from_a_broken_route(
    console: tuple[Console, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    state, base = console
    state.accepts = False

    code = main(["--base-url", base, "--username", USERNAME, "--password", PASSWORD])

    assert code == EXIT_REFUSED
    assert "sign in" in capsys.readouterr().err.lower()


def test_a_console_that_is_not_there_is_told_apart_from_a_broken_route(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Port 1 on the loopback interface: nothing is listening, and nothing may.
    code = main(["--base-url", "http://127.0.0.1:1", "--username", "u", "--password", "p"])

    assert code == EXIT_REFUSED
    assert capsys.readouterr().err.strip() != ""


def test_the_paths_can_be_listed_without_a_console(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list"]) == 0

    assert capsys.readouterr().out.split() == list(SHELL_PATHS)


def test_every_path_is_absolute_and_unique() -> None:
    assert len(set(SHELL_PATHS)) == len(SHELL_PATHS)
    assert all(path.startswith("/") for path in SHELL_PATHS)
    assert json.dumps(list(SHELL_PATHS))  # a plain list of strings, nothing clever
