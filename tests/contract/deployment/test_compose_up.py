"""The standard profile's stack, brought up for real — not just parsed.

``test_compose_profiles.py`` proves the compose file is internally
consistent; it has never asked Docker to start it. A file can declare a name,
a build context and a healthcheck and still not start — the postgres mount
defect this file exists to catch shipped for exactly that reason: every
static assertion about the file held, and the container still exited 1 on
its first real boot, from a volume that had never held a byte.

Skips cleanly with a named reason where there is no container runtime, the
same rule the visual and chaos suites already run under (see
``tests/contract/console/test_console_visual_regression.py`` and
``tests/chaos/test_chaos_suite.py``); a machine that has one turns the skip
into a run. ``make verify`` stays runnable with no container runtime at all
— this module is the only place in the deployment contract suite that needs
one, and it never runs unconditionally.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.contract.deployment.conftest import COMPOSE, REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.e2e]

needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason=(
        "this test brings up a real container with `docker compose up`; there is "
        "no container runtime on this machine"
    ),
)

_COMPOSE_FILE = COMPOSE / "docker-compose.yml"
_FILE_ARGS = ("--file", str(_COMPOSE_FILE))

#: Generous against the postgres healthcheck's own ceiling declared in the
#: compose file (20s start_period + 20 retries * 5s interval = 120s), so a
#: slow machine is a pass and not a flake.
_WAIT_TIMEOUT_SECONDS = 150

#: Generous against the full chain: postgres healthy (up to 120s) before
#: ``app`` can even start, then ``app``'s own healthcheck ceiling (40s
#: start_period + 3 retries * 15s interval = 85s) stacked on top, with
#: ``console`` and ``proxy`` racing the same clock rather than adding to it.
_STACK_WAIT_TIMEOUT_SECONDS = 320


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    """Run one ``docker compose`` invocation and return its result directly.

    Never through a shell pipe: this wave has already been bitten three times
    by a status read off the wrong end of a pipeline. ``CompletedProcess``
    carries the real exit code and both streams.
    """
    return subprocess.run(  # noqa: S603 — a fixed argv, no shell, no interpolation
        ["docker", "compose", *_FILE_ARGS, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_WAIT_TIMEOUT_SECONDS + 30,
        check=False,
    )


def _container_id(service: str) -> str:
    found = _compose("ps", "--quiet", service)
    container_id = found.stdout.strip()
    assert container_id, (
        f"`docker compose ps --quiet {service}` returned nothing; stderr:\n{found.stderr}"
    )
    return container_id


def _health(container_id: str) -> str:
    probe = subprocess.run(  # noqa: S603, S607 — fixed argv, no shell
        ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_id],
        capture_output=True,
        text=True,
        check=True,
    )
    return probe.stdout.strip()


@needs_docker
def test_the_standard_profiles_postgres_container_becomes_healthy_from_a_fresh_volume() -> None:
    """The exact defect, reproduced against the shipped file, nothing test-special.

    ``down --volumes`` first, so the volume this test starts from has never
    held a byte — the condition the postgres image's own upgrade-detector
    still misreads when the mount is wrong. The container's health is read
    directly with ``docker inspect`` rather than trusted from ``up --wait``'s
    exit code alone, which is the second, independent check the wave's own
    notes ask for.
    """
    _compose("down", "--volumes")
    try:
        result = _compose("up", "postgres", "--wait", "--wait-timeout", str(_WAIT_TIMEOUT_SECONDS))
        status = _health(_container_id("postgres"))
        assert result.returncode == 0 and status == "healthy", (
            f"`docker compose up postgres --wait` exited {result.returncode} "
            f"(health={status!r}); stderr:\n{result.stderr}"
        )
    finally:
        _compose("down", "--volumes")


def _restart_count(container_id: str) -> int:
    probe = subprocess.run(  # noqa: S603, S607 — fixed argv, no shell
        ["docker", "inspect", "--format", "{{.RestartCount}}", container_id],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(probe.stdout.strip())


@needs_docker
def test_the_standard_profiles_whole_project_boots_with_no_credential_at_all() -> None:
    """``docker compose up --wait`` on the whole project, exactly as the
    project's own README tells an operator to run it.

    Before the fix this covers, ``proxy`` and ``console`` crash-looped on
    every real boot with ``[fatal] NINJASRE_LLM_PROVIDER: No model provider
    is configured`` — a defect no static assertion about the compose file
    could see, and one ``test_..._postgres_container_becomes_healthy...``
    above never exercises because it starts postgres alone. ``ollama`` is the
    one supported provider ``PROVIDER_CREDENTIAL_ENV`` demands no credential
    for, so the whole stack comes up from one environment variable and no
    secret at all — the shape an operator gets on a first, credential-free
    try.

    Health is read directly with ``docker inspect`` for all four containers,
    never through ``up --wait``'s own exit code alone. ``RestartCount`` is
    read too and asserted at zero: a container that crash-looped five times
    before recovering would still end up healthy, and would still be the
    defect this test exists to catch.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("NINJASRE_LLM_PROVIDER", "ollama")
    try:
        _compose("down", "--volumes")
        try:
            result = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
                [
                    "docker",
                    "compose",
                    *_FILE_ARGS,
                    "up",
                    "--build",  # the images this machine already has may predate this tree
                    "--wait",
                    "--wait-timeout",
                    str(_STACK_WAIT_TIMEOUT_SECONDS),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=_STACK_WAIT_TIMEOUT_SECONDS + 300,
                check=False,
            )

            services = ("postgres", "proxy", "app", "console")
            container_ids = {service: _container_id(service) for service in services}
            health = {service: _health(cid) for service, cid in container_ids.items()}
            restarts = {service: _restart_count(cid) for service, cid in container_ids.items()}

            assert result.returncode == 0 and all(
                status == "healthy" for status in health.values()
            ), (
                f"`docker compose up --wait` exited {result.returncode}; "
                f"health={health}; stderr:\n{result.stderr}"
            )
            assert restarts == dict.fromkeys(services, 0), (
                f"a service restarted before becoming healthy, which is what a "
                f"crash-loop that eventually recovers looks like: {restarts}"
            )
        finally:
            _compose("down", "--volumes")
    finally:
        monkeypatch.undo()
