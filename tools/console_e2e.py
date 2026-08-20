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
    Run by its own CI job rather than by every ``make verify``. The stack comes
    up with an empty database, so it is seeded with the same demonstration
    dataset the mock plane serves — through ``setup load-demo``, the command an
    operator runs on a fresh deployment, not a route built for this harness.
    Needs a model provider configured in the environment, the same prerequisite
    the compose file's own header names for any ``docker compose up``.

Neither the browser nor the ports are assumed. The browser is provisioned
through the same toolchain that provisions Node, so a checkout that never ran
``make console-setup`` gets one instead of sixty launch failures; the ports are
the pinned ones when they are free and the kernel's choice when they are not, so
a second checkout running its suite at the same time is a slower run rather than
a suite driving somebody else's console.

Usage::

    python -m tools.console_e2e run
    python -m tools.console_e2e run --backing compose
    python -m tools.console_e2e run --repeat 20

Exits 0 when the suite passed, 1 when it did not, and 2 when the toolchain, the
browser or the backing could not be brought up — which is a different failure
and says so.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from config.constants.console import (
    CONSOLE_E2E_MOCK_PORT,
    CONSOLE_E2E_PORT,
    NINJASRE_CONSOLE_API_URL_ENV,
    NINJASRE_CONSOLE_BASE_URL_ENV,
    NINJASRE_CONSOLE_E2E_CREDENTIAL_ENV,
)
from config.constants.first_run import NINJASRE_ORGANISATION_ENV
from config.constants.fixtures import (
    DEFAULT_FIXTURE_SCENARIO,
    FIXTURE_ROOT_DIR_NAME,
    NINJASRE_FIXTURE_ROOT_ENV,
)
from platform.startup.demo.dataset import load_dataset
from tools.console_toolchain import (
    REPO_ROOT,
    Toolchain,
    ToolchainError,
    console_root,
    ensure_browsers,
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


@dataclass(frozen=True, slots=True)
class Backing:
    """Where the gateway answers, and a credential to sign in with.

    The mock plane accepts any credential at all — see
    ``console/tests/e2e/session.ts`` — so it mints none. The compose backing is
    a real gateway behind a real guard, so it exchanges the bootstrap
    credential ``bring_up`` issued for a durable one the browser can actually
    sign in with, and hands that back here.
    """

    api_url: str
    credential: str | None = None


def ports(*preferred: int) -> tuple[int, ...]:
    """Return one free loopback port per entry in ``preferred``.

    Each pinned port is used when it is free and replaced by one the kernel
    picks when it is not, so two checkouts of this repository can run their
    suites at the same time. That is not a convenience — it is the difference
    between a failure and a wrong answer.

    A fixed port is silently wrong under concurrency rather than loudly broken.
    ``_wait_for`` asks whether *something* is listening, and something is: the
    other checkout's console. Our own server exits with ``EADDRINUSE`` a moment
    later, the wait has already succeeded against the stranger, and a suite then
    reports on a build nobody asked it about — green or red for reasons that are
    not in this working tree.

    Every port is reserved before any is returned, so two servers in one run
    cannot be handed the same one. The sockets are closed on the way out, which
    leaves the usual check-then-bind gap; it is a few milliseconds against a
    listener that lives for minutes, and the loser gets ``EADDRINUSE`` on a port
    no other console is serving, which is the honest failure.
    """
    reserved: list[socket.socket] = []
    try:
        for want in preferred:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            reserved.append(probe)
            try:
                probe.bind(("127.0.0.1", want))
            except OSError:
                # Taken, by another checkout's run or by anything else. A port
                # of the kernel's choosing is as good for a suite that is told
                # its own address.
                probe.bind(("127.0.0.1", 0))
        return tuple(probe.getsockname()[1] for probe in reserved)
    finally:
        for probe in reserved:
            probe.close()


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


def _container_health(base: Sequence[str], service: str) -> str | None:
    """Return one compose service's container health, or ``None`` if it has none yet."""
    found = subprocess.run(
        [*base, "ps", "--quiet", service], capture_output=True, text=True, check=False
    )
    container_id = found.stdout.strip()
    if not container_id:
        return None
    probe = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.stdout.strip() or None


def _wait_for_service_healthy(base: Sequence[str], service: str) -> None:
    """Block until one compose service reports healthy, or raise saying why not.

    Polled directly with ``docker inspect``, one service at a time, rather than
    through ``up --wait`` for the whole project. ``--wait`` watches every
    container the compose file starts, including ones this harness never talks
    to — and a service that fails its own configuration check for a reason that
    has nothing to do with the gateway would otherwise block every backing this
    function exists to provide, forever, regardless of what this harness
    actually needs running.
    """
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        health = _container_health(base, service)
        if health == "healthy":
            return
        if health == "unhealthy":
            raise HarnessError(f"the compose {service!r} container is unhealthy")
        time.sleep(_POLL_SECONDS)
    raise HarnessError(
        f"the compose {service!r} container did not become healthy within "
        f"{_STARTUP_TIMEOUT_SECONDS:.0f}s"
    )


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
def mock_plane(scenario: str, port: int) -> Iterator[Backing]:
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
        yield Backing(api_url=url)


#: Where the fixture tree lands inside the ``app`` container. Under ``/tmp``
#: because it is scratch for this one run, never a path anything else in the
#: image reserves.
_CONTAINER_FIXTURE_ROOT: Final = "/tmp/fixtures"


def _seed(base: Sequence[str]) -> None:
    """Load the demonstration dataset into a freshly-started compose stack.

    Runs ``setup load-demo`` inside the ``app`` container — the exact command
    named in ``surfaces/cli/commands/setup.py``, the one an operator runs on a
    fresh deployment. Nothing here is a route or a code path built for this
    harness.

    The deployment image never ships ``fixtures/`` (it is data, not one of the
    packaged tiers — see the root ``AGENTS.md``), so the tree this process's own
    checkout already holds is copied in first. ``NINJASRE_FIXTURE_ROOT`` is not
    a harness invention either: it is the setting ``load_dataset`` names in its
    own refusal message for exactly this case, "the fixture tree lives
    elsewhere in this deployment".

    Raises:
        HarnessError: the copy or the seeding command failed.
    """
    try:
        subprocess.run(
            [*base, "cp", str(REPO_ROOT / FIXTURE_ROOT_DIR_NAME), f"app:{_CONTAINER_FIXTURE_ROOT}"],
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run(
            [
                *base,
                "exec",
                "--env",
                f"{NINJASRE_FIXTURE_ROOT_ENV}={_CONTAINER_FIXTURE_ROOT}",
                "app",
                "ninjasre",
                "setup",
                "load-demo",
            ],
            check=True,
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as error:
        raise HarnessError(f"seeding the compose stack failed: {error}") from error


def _bootstrap_secret(base: Sequence[str]) -> str:
    """Return the bootstrap credential's secret, read through the CLI itself.

    ``ninjasre --json setup credential`` — the exact command an operator who
    closed the terminal before reading the token runs, never the host state
    file directly: this harness has no more of a right to reach into that file
    than an operator does.

    Raises:
        HarnessError: there is no bootstrap credential to read, or the command
            failed.
    """
    found = subprocess.run(
        [*base, "exec", "app", "ninjasre", "--json", "setup", "credential"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if found.returncode != 0:
        raise HarnessError(
            "reading the bootstrap credential failed: "
            f"{found.stderr.strip() or found.stdout.strip()}"
        )
    try:
        envelope = json.loads(found.stdout)
        secret = envelope["data"]["secret"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise HarnessError(
            f"the bootstrap credential envelope carried no secret: {found.stdout!r}"
        ) from error
    if not isinstance(secret, str) or secret == "":
        raise HarnessError(f"the bootstrap credential envelope carried no secret: {envelope!r}")
    return secret


#: Who the browser harness identifies as, exchanging the bootstrap credential
#: for a durable one. Not a real operator — a fixed identity this harness owns,
#: same as any other automated caller of the first-run route.
_HARNESS_PRINCIPAL: Final = {
    "user_id": "console-e2e",
    "email": "console-e2e@ninjasre.invalid",
    "display_name": "Console end-to-end harness",
}


def _durable_secret(api_url: str, bootstrap_secret: str) -> str:
    """Exchange the bootstrap credential for one the browser can sign in with.

    Calls the exact route a real first sign-in calls,
    ``POST /v1/setup/durable-credential`` — never a shortcut invented for this
    harness. Spends the bootstrap credential, the same as a real exchange
    would.

    Raises:
        HarnessError: the exchange was refused.
    """
    request = urllib.request.Request(
        f"{api_url}/v1/setup/durable-credential",
        data=json.dumps(_HARNESS_PRINCIPAL).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {bootstrap_secret}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            issued = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise HarnessError(
            f"exchanging the bootstrap credential failed: {error.code} {detail}"
        ) from error
    secret = issued.get("secret")
    if not isinstance(secret, str) or secret == "":
        raise HarnessError(f"the durable credential response carried no secret: {issued!r}")
    return secret


@contextlib.contextmanager
def compose_stack() -> Iterator[Backing]:
    """Bring the deployment's own compose stack up and yield the gateway's address.

    The same file the deployment ships, with no test-only override: a stack
    assembled differently from the one an operator runs is a stack that proves
    something about a configuration nobody has. Every one of its four services
    is started, exactly as ``docker compose up`` with no service list would
    start them. Seeding happens after the stack is already up, through the same
    command line an operator has — it does not change what was assembled, only
    what the running deployment is asked to do with it.

    Readiness is judged by ``postgres`` and ``app`` alone, polled directly
    rather than through ``up --wait`` — see ``_wait_for_service_healthy`` for
    why the blanket form cannot be used here today.

    The tenant this harness signs into is the demonstration dataset's own, not
    the compose file's unqualified default: without this, bring-up creates
    ``default`` while the seeded dataset lands in the tenant its own
    configuration tree declares, and a browser signed into the former would see
    an organisation nothing was ever written into.
    """
    docker = shutil.which("docker")
    if docker is None:
        raise HarnessError("the compose backing needs a container runtime and there is none")

    compose_file = REPO_ROOT / "deploy" / "compose" / "docker-compose.yml"
    base = [docker, "compose", "--file", str(compose_file)]
    tenant = load_dataset().organisation_id
    up_environment = {**os.environ, NINJASRE_ORGANISATION_ENV: tenant}
    # One try/finally around the whole sequence, not the ``up`` call alone: a
    # container that failed its own health check, or a seeding step that
    # failed partway, still leaves something running. ``down --volumes`` is
    # harmless to run over a project nothing was ever created for.
    try:
        # ``--build`` rather than plain ``up``: compose reuses an existing image,
        # so without it the stack serves whatever the image was built from and
        # the run reports a confident answer about code nobody has. That cost a
        # slice of this feature nine red assertions against a backend image
        # built before the routes it was being asked about existed. Rebuilding
        # is cheap when nothing changed, because the layers cache.
        subprocess.run(
            [*base, "up", "--build", "--detach"], check=True, cwd=REPO_ROOT, env=up_environment
        )
        _wait_for_service_healthy(base, "postgres")
        _wait_for_service_healthy(base, "app")
        _seed(base)
        credential = _durable_secret(_COMPOSE_API_URL, _bootstrap_secret(base))
        yield Backing(api_url=_COMPOSE_API_URL, credential=credential)
    except subprocess.CalledProcessError as error:
        raise HarnessError(f"the compose stack did not come up: {error}") from error
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
    credential: str | None = None,
    extra: Sequence[str] = (),
) -> int:
    """Run one Playwright project against ``base_url`` and return its exit status.

    ``credential``, when given, is what ``console/tests/e2e/session.ts`` signs
    into the browser instead of the mock-plane value it otherwise falls back
    to — see ``NINJASRE_CONSOLE_E2E_CREDENTIAL_ENV``.
    """
    env = environment(toolchain)
    env[NINJASRE_CONSOLE_BASE_URL_ENV] = base_url
    if credential is not None:
        env[NINJASRE_CONSOLE_E2E_CREDENTIAL_ENV] = credential
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
        ToolchainError: the toolchain or the browser could not be provisioned.
            Distinct from a failing suite all the way out to the exit status,
            because "no browser" is a thing to install and "a test failed" is a
            thing to fix.
    """
    toolchain = resolve()
    ensure_browsers(toolchain)

    mock_port, console_port = ports(CONSOLE_E2E_MOCK_PORT, CONSOLE_E2E_PORT)
    backing_context = compose_stack() if backing == "compose" else mock_plane(scenario, mock_port)
    with backing_context as target, console(toolchain, target.api_url, console_port) as base_url:
        # Named, because under concurrency these are not the pinned ports and a
        # reader of the log should not have to guess which console was driven.
        print(f"driving the console at {base_url} against {target.api_url}", flush=True)
        for attempt in range(1, repeat + 1):
            if repeat > 1:
                print(f"--- run {attempt} of {repeat} ---", flush=True)
            status = playwright(
                toolchain, project, base_url, credential=target.credential, extra=extra
            )
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
