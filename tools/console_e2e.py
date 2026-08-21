"""Start what the browser tests need, run them, and take it down again.

A browser test that also owns process lifecycle is a browser test that hangs, so
the lifecycle lives here instead. Two backings are supported, and they answer
different questions:

``mock``
    The committed dataset, served by ``tools.mockplane``. Deterministic by
    construction — every timestamp in it is shifted to one fixed instant — which
    is what makes a twenty-run determinism sweep a thing worth running. This is
    the backing the gate uses.

``compose``
    The deployment's own compose definition: a real gateway against a real
    database. Slower, needs a container runtime, and is the one that would catch
    a console which works against the dataset and not against the application.
    Run by its own CI job rather than by every ``make verify``.

Usage::

    python -m tools.console_e2e run
    python -m tools.console_e2e run --backing compose
    python -m tools.console_e2e run --repeat 20

Exits 0 when the suite passed, 1 when it did not, and 2 when the toolchain or
the backing could not be brought up — which is a different failure and says so.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from typing import Final

from config.constants.console import (
    CONSOLE_E2E_MOCK_PORT,
    CONSOLE_E2E_PORT,
    NINJASRE_CONSOLE_API_URL_ENV,
    NINJASRE_CONSOLE_BASE_URL_ENV,
)
from config.constants.fixtures import DEFAULT_FIXTURE_SCENARIO
from tools.console_toolchain import (
    REPO_ROOT,
    Toolchain,
    ToolchainError,
    console_root,
    environment,
    resolve,
)

#: How long a service gets to answer before we call it dead. Generous, because
#: the console's first request compiles a route; short enough that a hung
#: process fails the run rather than occupying a runner.
_STARTUP_TIMEOUT_SECONDS: Final = 120.0

#: How long a terminated service gets to exit before it is killed.
_SHUTDOWN_TIMEOUT_SECONDS: Final = 20.0

_POLL_SECONDS: Final = 0.25

#: Where the compose stack serves the gateway, as the host sees it.
_COMPOSE_API_URL: Final = "http://127.0.0.1:8420"


class HarnessError(RuntimeError):
    """The backing or the console could not be started, so nothing was run."""


def _answers(url: str) -> bool:
    """Return whether ``url`` answers at all — any status, including a refusal."""
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        # A 404 or a 401 is a server. What we are waiting for is a listener.
        return True
    except (urllib.error.URLError, OSError):
        return False


def _wait_for(url: str, process: subprocess.Popen[bytes], what: str) -> None:
    """Block until ``url`` answers, or raise saying what failed to come up."""
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise HarnessError(f"{what} exited with {process.returncode} before serving {url}")
        if _answers(url):
            return
        time.sleep(_POLL_SECONDS)
    raise HarnessError(f"{what} did not serve {url} within {_STARTUP_TIMEOUT_SECONDS:.0f}s")


@contextlib.contextmanager
def _terminating(process: subprocess.Popen[bytes]) -> Iterator[subprocess.Popen[bytes]]:
    """Yield ``process`` and make sure it is gone afterwards, killed if need be."""
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@contextlib.contextmanager
def mock_plane(scenario: str, port: int) -> Iterator[str]:
    """Serve the committed dataset and yield the address it answers on."""
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.mockplane",
            "serve",
            "--scenario",
            scenario,
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    with _terminating(process):
        _wait_for(f"{url}/v1/runs", process, "the mock data plane")
        yield url


@contextlib.contextmanager
def compose_stack() -> Iterator[str]:
    """Bring the deployment's own compose stack up and yield the gateway's address.

    The same file the deployment ships, with no test-only override: a stack
    assembled differently from the one an operator runs is a stack that proves
    something about a configuration nobody has.
    """
    docker = shutil.which("docker")
    if docker is None:
        raise HarnessError("the compose backing needs a container runtime and there is none")

    compose_file = REPO_ROOT / "deploy" / "compose" / "docker-compose.yml"
    base = [docker, "compose", "--file", str(compose_file)]
    try:
        subprocess.run([*base, "up", "--detach", "--wait"], check=True, cwd=REPO_ROOT)
    except subprocess.CalledProcessError as error:
        raise HarnessError(f"the compose stack did not come up: {error}") from error
    try:
        yield _COMPOSE_API_URL
    finally:
        subprocess.run([*base, "down", "--volumes"], check=False, cwd=REPO_ROOT)


@contextlib.contextmanager
def console(toolchain: Toolchain, api_url: str, port: int) -> Iterator[str]:
    """Serve the built console against ``api_url`` and yield its address."""
    # The standalone output, not the development server: what the browser tests
    # drive has to be the artefact the deployment runs, or they are testing a
    # second console nobody ships.
    server = console_root() / ".next" / "standalone" / "server.js"
    if not server.is_file():
        raise HarnessError(f"{server} is missing; run `make console-build` first")

    url = f"http://127.0.0.1:{port}"
    env = environment(toolchain)
    env[NINJASRE_CONSOLE_API_URL_ENV] = api_url
    env["HOSTNAME"] = "127.0.0.1"
    env["PORT"] = str(port)
    process = subprocess.Popen([str(toolchain.node), str(server)], cwd=server.parent, env=env)
    with _terminating(process):
        _wait_for(url, process, "the console")
        yield url


def playwright(
    toolchain: Toolchain,
    project: str,
    base_url: str,
    *,
    extra: Sequence[str] = (),
) -> int:
    """Run one Playwright project against ``base_url`` and return its exit status."""
    env = environment(toolchain)
    env[NINJASRE_CONSOLE_BASE_URL_ENV] = base_url
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(console_root() / ".toolchain" / "browsers"))
    finished = subprocess.run(
        [
            str(toolchain.node),
            str(toolchain.pnpm),
            "exec",
            "playwright",
            "test",
            f"--project={project}",
            *extra,
        ],
        cwd=console_root(),
        env=env,
        check=False,
    )
    return finished.returncode


def run(
    *,
    backing: str = "mock",
    scenario: str = DEFAULT_FIXTURE_SCENARIO,
    project: str = "behaviour",
    repeat: int = 1,
    extra: Sequence[str] = (),
) -> int:
    """Bring the backing and the console up, run ``project``, and return its status.

    Raises:
        HarnessError: something failed to come up, so nothing was run.
    """
    toolchain = resolve()
    backing_context = (
        compose_stack() if backing == "compose" else mock_plane(scenario, CONSOLE_E2E_MOCK_PORT)
    )
    with backing_context as api_url, console(toolchain, api_url, CONSOLE_E2E_PORT) as base_url:
        for attempt in range(1, repeat + 1):
            if repeat > 1:
                print(f"--- run {attempt} of {repeat} ---", flush=True)
            status = playwright(toolchain, project, base_url, extra=extra)
            if status != 0:
                return status
    return 0


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_e2e", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run", help="run a browser suite against a backing")
    runner.add_argument("--backing", choices=("mock", "compose"), default="mock")
    runner.add_argument("--scenario", default=DEFAULT_FIXTURE_SCENARIO)
    runner.add_argument("--project", default="behaviour")
    runner.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="run the suite this many times; the determinism sweep runs it twenty",
    )
    runner.add_argument("rest", nargs=argparse.REMAINDER)

    arguments = parser.parse_args(argv)
    try:
        return run(
            backing=arguments.backing,
            scenario=arguments.scenario,
            project=arguments.project,
            repeat=arguments.repeat,
            extra=[part for part in arguments.rest if part != "--"],
        )
    except (HarnessError, ToolchainError) as error:
        print(f"console end-to-end: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
