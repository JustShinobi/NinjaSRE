"""Bringing up the PostgreSQL the contract suite runs its second backend against.

Three ways to get a database, tried in order, because the three situations a
contributor is in are genuinely different.

**An operator-provided URL** (``NINJASRE_TEST_DATABASE_URL``). CI with a service
container, or a developer who already has one running. Fastest, and the only
option where the suite is not allowed to assume it may create databases.

**Docker.** The image in ``postgres.Dockerfile`` — Apache's AGE image with
pgvector added — built once and reused. Nothing published carries both
extensions, so the suite builds it rather than pretending one exists.

**Neither.** The suite runs against the fakes alone and *says so*. It does not
skip silently: a run that only exercised one backend has not shown that the
ports have two implementations, and `test_backends_available` is what makes
that visible in the output rather than in nobody's memory.

Each session gets its own database inside the instance, dropped afterwards. A
suite that shared one would pass in isolation and fail when two ran at once,
which is the worst kind of test failure to debug.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from config.constants.persistence import NINJASRE_TEST_DATABASE_URL_ENV
from platform.persistence.postgres.crypto import KEY_RING, decode_key, generate_key
from platform.persistence.postgres.engine import create_engine, ensure_extensions
from platform.persistence.postgres.gateway import PostgresPersistence

HERE = Path(__file__).resolve().parent

#: Tag for the locally built image. Pinned rather than ``latest`` so a rebuild
#: is a deliberate act.
IMAGE_TAG = "ninjasre-postgres-test:16"

CONTAINER_NAME = "ninjasre-contract-postgres"
CONTAINER_PORT = 55433
CONTAINER_PASSWORD = "ninjasre"


@dataclass(frozen=True, slots=True)
class Backend:
    """How the suite reached a PostgreSQL, for reporting."""

    url: str
    source: str


def _docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a docker command.

    Through ``sg`` when the process's groups do not yet include ``docker``,
    which is the state a shell is in for the rest of the session after the group
    was granted. Falling back rather than failing means a contributor who has
    just been added to the group does not have to log out to run the suite.
    """
    command = ["docker", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 and "permission denied" in result.stderr.lower():
        quoted = " ".join(command)
        result = subprocess.run(
            ["sg", "docker", "-c", quoted], capture_output=True, text=True, check=False
        )
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return result


def docker_available() -> bool:
    """Return whether a Docker daemon will talk to us."""
    try:
        return _docker("info", check=False).returncode == 0
    except (OSError, RuntimeError):
        return False


def start_container() -> str:
    """Build the image if needed, start the instance, and return its URL."""
    _docker("build", "-f", str(HERE / "postgres.Dockerfile"), "-t", IMAGE_TAG, str(HERE))
    _docker("rm", "-f", CONTAINER_NAME, check=False)
    _docker(
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "-e",
        f"POSTGRES_PASSWORD={CONTAINER_PASSWORD}",
        "-e",
        "POSTGRES_USER=ninjasre",
        "-e",
        "POSTGRES_DB=ninjasre",
        "-p",
        f"{CONTAINER_PORT}:5432",
        IMAGE_TAG,
    )

    _await_readiness()
    return f"postgresql://ninjasre:{CONTAINER_PASSWORD}@127.0.0.1:{CONTAINER_PORT}/ninjasre"


def _await_readiness() -> None:
    """Block until the server is accepting TCP connections, and staying up.

    Over TCP, and twice, and neither is superstition.

    PostgreSQL's entrypoint starts a *temporary* server to run the scripts in
    ``docker-entrypoint-initdb.d`` — the ones that install our extensions — then
    shuts it down and starts the real one. That temporary server listens on the
    unix socket only, so a plain ``pg_isready`` reports ready during the window
    when the next thing to happen is a restart. The suite then connects, and the
    restart drops it: ``ConnectionResetError``, on whichever test happened to be
    first.

    Requiring TCP skips the temporary server entirely. Requiring two
    consecutive successes covers the moment between the temporary server
    stopping and the real one binding.
    """
    consecutive = 0
    for _ in range(90):
        ready = _docker(
            "exec",
            CONTAINER_NAME,
            "pg_isready",
            "--host",
            "127.0.0.1",
            "--port",
            "5432",
            "-U",
            "ninjasre",
            "-d",
            "ninjasre",
            check=False,
        )
        consecutive = consecutive + 1 if ready.returncode == 0 else 0
        if consecutive >= 2:
            return
        _sleep()

    raise RuntimeError("The test database did not become ready.")


def stop_container() -> None:
    """Remove the instance this module started."""
    _docker("rm", "-f", CONTAINER_NAME, check=False)


def _sleep() -> None:
    import time

    time.sleep(1.0)


def discover() -> Backend | None:
    """Return the PostgreSQL the suite should use, or ``None`` if there is none."""
    configured = os.environ.get(NINJASRE_TEST_DATABASE_URL_ENV)
    if configured:
        return Backend(url=configured, source="NINJASRE_TEST_DATABASE_URL")
    if docker_available():
        return Backend(url=start_container(), source="docker")
    return None


@asynccontextmanager
async def scratch_database(backend: Backend) -> AsyncIterator[str]:
    """Create a database for one test session, and drop it afterwards."""
    name = f"ninjasre_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(backend.url)

    # AUTOCOMMIT because CREATE DATABASE cannot run inside a transaction, and
    # SQLAlchemy opens one by default.
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'CREATE DATABASE "{name}"'))

    scratch = _swap_database(backend.url, name)
    try:
        yield scratch
    finally:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            # FORCE closes the connections the pool did not get round to
            # releasing. Without it the drop blocks and the session hangs at
            # teardown, which reads as a test that never finished.
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


def _swap_database(url: str, name: str) -> str:
    """Return ``url`` pointed at a different database on the same server."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


def _database_of(url: str) -> str:
    """Return the database name a URL points at."""
    return url.rpartition("/")[2]


def dump_and_restore_available() -> bool:
    """Return whether ``pg_dump`` and ``psql`` can be reached somehow."""
    if shutil.which("pg_dump") and shutil.which("psql"):
        return True
    return _docker("inspect", CONTAINER_NAME, check=False).returncode == 0


def _run_client(tool: str, url: str, *arguments: str, stdin: str | None = None) -> str:
    """Run a PostgreSQL client program, on the host or inside our container.

    Preferring the host's binaries means a CI job with the client tools
    installed exercises the same command an operator would type. Falling back
    into the container means a developer who has Docker and nothing else still
    runs the test rather than skipping it.
    """
    if shutil.which(tool):
        result = subprocess.run(
            [tool, url, *arguments],
            capture_output=True,
            text=True,
            input=stdin,
            check=False,
        )
    else:
        inner = f"postgresql://ninjasre:{CONTAINER_PASSWORD}@127.0.0.1:5432/{_database_of(url)}"
        result = (
            _docker(
                "exec",
                "-i",
                CONTAINER_NAME,
                tool,
                inner,
                *arguments,
                check=False,
            )
            if stdin is None
            else _docker_with_stdin(["exec", "-i", CONTAINER_NAME, tool, inner, *arguments], stdin)
        )

    if result.returncode != 0:
        raise RuntimeError(f"{tool} failed: {result.stderr.strip()[:400]}")
    return result.stdout


def _docker_with_stdin(arguments: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
    """Run a docker command that reads from standard input."""
    command = ["docker", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, input=stdin, check=False)
    if result.returncode != 0 and "permission denied" in result.stderr.lower():
        result = subprocess.run(
            ["sg", "docker", "-c", " ".join(command)],
            capture_output=True,
            text=True,
            input=stdin,
            check=False,
        )
    return result


def dump_database(url: str) -> str:
    """Return a plain-text ``pg_dump`` of the database ``url`` names.

    Plain text rather than the custom format, because it is what the operator
    documentation tells an operator to take and what a restore into a *clean*
    database consumes with ``psql`` alone. A backup procedure that needs a
    second tool to read it is one more thing to get wrong at 3am.
    """
    return _run_client("pg_dump", url, "--no-owner", "--no-privileges")


def restore_database(url: str, dump: str) -> None:
    """Restore ``dump`` into the database ``url`` names."""
    _run_client("psql", url, "--quiet", "--set", "ON_ERROR_STOP=1", stdin=dump)


async def create_database(backend: Backend, name: str, *, template: str = "template0") -> str:
    """Create an extra database on the same server, and return its URL.

    From ``template0`` by default, which is what "restore into a clean
    database" has to mean for this schema. A NinjaSRE dump carries ``CREATE
    SCHEMA ag_catalog`` — Apache AGE puts its catalogue there and ``pg_dump``
    faithfully captures it — so restoring into a database that *already* has the
    extensions fails on the first statement. ``template0`` is the pristine
    template that has nothing in it, and it is what the operator documentation
    tells an operator to use for exactly this reason.
    """
    admin = create_engine(backend.url)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}" TEMPLATE {template}'))
    await admin.dispose()
    return _swap_database(backend.url, name)


async def drop_database(backend: Backend, name: str) -> None:
    """Remove a database created by ``create_database``."""
    admin = create_engine(backend.url)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


async def build_gateway(url: str) -> PostgresPersistence:
    """Return a migrated, extension-ready gateway over ``url``."""
    if not KEY_RING.is_configured:
        # A key per test run. Credentials are encrypted with it and the database
        # is dropped afterwards, so nothing outlives the process that made it.
        KEY_RING.configure(decode_key(generate_key()))

    gateway = PostgresPersistence.from_url(url)
    async with gateway.engine.begin() as conn:
        await ensure_extensions(conn)
    await gateway.start()
    return gateway


__all__ = [
    "CONTAINER_NAME",
    "IMAGE_TAG",
    "Backend",
    "build_gateway",
    "create_database",
    "discover",
    "docker_available",
    "drop_database",
    "dump_and_restore_available",
    "dump_database",
    "restore_database",
    "scratch_database",
    "start_container",
    "stop_container",
]
