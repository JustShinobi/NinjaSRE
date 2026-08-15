"""Open every screen of the console, signed in, and refuse a deploy that cannot.

The canary's smoke checks all pointed at the API — liveness, readiness, the
OpenAPI document, the store's health. Every one of them passed on a release in
which two of the fourteen shell routes answered HTTP 500 to an operator with
every permission there is. The checks were not wrong; they were not looking at
the console.

So this signs in the way a person does, walks every route the shell declares,
and requires 200 from each. It is fourteen requests against a process that is
already running, which is a smaller price than a screen nobody can open.

It lives here rather than in the guest's own checks because the guest has no
Node and no console build, and it speaks HTTP and nothing else: no first-party
import beyond the constants tier, no client, no browser.

Usage::

    python -m tools.console_smoke --base-url http://10.0.0.4:8421 \\
        --username avery --password ...
    python -m tools.console_smoke --list

Exits 0 when every route answered 200, 1 when one did not, and 2 when the walk
could not be started at all — a console that is not there, or a sign-in that was
refused. A deploy flow reads the difference: the first is a broken release, the
second is a broken invocation.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import httpx

from config.constants.console import CONSOLE_SESSION_COOKIE, CONSOLE_SESSION_ENDPOINT

#: Every route of the shell, exactly as ``console/src/shell/routes.ts`` declares
#: them.
#:
#: Restated rather than imported, because that manifest is TypeScript and this is
#: not. ``tests/contract/console/test_console_shell.py`` asserts this tuple equal
#: to the manifest in both directions, so a fifteenth area is either walked here
#: or fails the gate — which is the only reason a restatement is allowed to
#: exist.
SHELL_PATHS: Final[tuple[str, ...]] = (
    "/",
    "/incidents",
    "/runs",
    "/decisions",
    "/resources",
    "/knowledge",
    "/agent",
    # A task rather than a place, and walked like every other route anyway: it
    # sits inside the shell, it is reachable by address, and the deployment it
    # renders for is the one with nothing configured — which is the state a
    # release is most likely to break and least likely to be tried in.
    "/first-run",
    "/integrations",
    "/integrations/not-covered",
    "/signals",
    "/autonomy",
    "/configuration",
    "/administration",
)

#: How long any one request may take. Generous: a cold Next.js route compiles on
#: its first request, and a walk that timed out on that would fail a release for
#: being new rather than for being broken.
REQUEST_TIMEOUT_SECONDS: Final = 30.0

#: The walk never started: nothing was listening, or the credentials were not
#: accepted. Told apart from a route that answered badly, because only one of
#: the two is the release's fault.
EXIT_REFUSED: Final = 2


class NotWalkable(Exception):
    """The walk could not be started, and why."""


@dataclass(frozen=True)
class Result:
    """One route, and what it answered."""

    path: str
    status: int

    @property
    def ok(self) -> bool:
        return self.status == 200


def sign_in(client: httpx.Client, username: str, password: str) -> str:
    """Return the session credential a username and a password establish.

    The console's own sign-in handler is used rather than the gateway's, because
    what this needs is the thing a browser would hold: the handler exchanges the
    pair for a token and sets it as the session cookie. Asking the gateway
    directly would walk the routes with a credential the console never issued,
    and would pass on a deployment whose sign-in is broken.
    """
    try:
        answer = client.post(
            CONSOLE_SESSION_ENDPOINT,
            data={"username": username, "password": password, "returnTo": "/"},
        )
    except httpx.HTTPError as error:
        raise NotWalkable(
            f"the console at {client.base_url} could not be reached: {error}"
        ) from error

    credential = answer.cookies.get(CONSOLE_SESSION_COOKIE)
    if credential is None or credential == "":
        raise NotWalkable(
            "the console refused the sign in: it answered "
            f"{answer.status_code} and set no session cookie"
        )
    return credential


def walk(
    base_url: str,
    username: str,
    password: str,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> tuple[Result, ...]:
    """Return what every shell route answered for a signed-in operator.

    Redirects are never followed. A console that bounced the walk to its sign-in
    page would otherwise answer 200 for all fourteen routes and report a
    deployment nobody can use as healthy.
    """
    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        credential = sign_in(client, username, password)
        # Held on the client rather than passed per request: one jar, and the
        # walk cannot accidentally make a request without it.
        client.cookies.set(CONSOLE_SESSION_COOKIE, credential)
        results: list[Result] = []
        for path in SHELL_PATHS:
            try:
                answer = client.get(path)
            except httpx.HTTPError as error:
                raise NotWalkable(f"{path} could not be requested: {error}") from error
            results.append(Result(path=path, status=answer.status_code))
        return tuple(results)


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="console_smoke",
        description="Open every screen of the console and require 200 from each.",
    )
    parser.add_argument("--base-url", help="where the console is listening")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument(
        "--timeout",
        type=float,
        default=REQUEST_TIMEOUT_SECONDS,
        help="seconds any one request may take",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the routes that would be walked, and walk none of them",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Walk the shell, report every route that did not answer 200."""
    options = _parse(sys.argv[1:] if argv is None else argv)

    if options.list:
        for path in SHELL_PATHS:
            print(path)
        return 0

    missing = [
        name
        for name in ("base_url", "username", "password")
        if getattr(options, name) in (None, "")
    ]
    if missing:
        print(
            "console_smoke needs " + ", ".join(f"--{name.replace('_', '-')}" for name in missing),
            file=sys.stderr,
        )
        return EXIT_REFUSED

    try:
        results = walk(options.base_url, options.username, options.password, options.timeout)
    except NotWalkable as refusal:
        print(str(refusal), file=sys.stderr)
        return EXIT_REFUSED

    for result in results:
        print(f"  {'ok     ' if result.ok else 'FAILED '} {result.path} ({result.status})")
    # Two streams, one report: without this the summary below overtakes the
    # walk it is summarising, and the reader is told which routes failed before
    # being shown any.
    sys.stdout.flush()

    broken = [result for result in results if not result.ok]
    if broken:
        print(
            f"{len(broken)} of {len(results)} console routes did not answer 200: "
            + ", ".join(f"{result.path} ({result.status})" for result in broken),
            file=sys.stderr,
        )
        return 1

    print(f"all {len(results)} console routes answered 200")
    return 0


if __name__ == "__main__":  # pragma: no cover — the module's entry point
    raise SystemExit(main())
