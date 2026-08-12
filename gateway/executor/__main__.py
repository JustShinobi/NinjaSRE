"""Running the executor: the process that holds the SSH identity.

Separate from the gateway for the reason the credential proxy is separate. The
thing that can authenticate is not the thing that decides what to ask for, and
keeping them in one process makes that distinction a convention rather than a
boundary.

**It refuses to start without an identity.** A deployment whose executor came up
without a key would answer every request with "could not reach the node", which
reads as a cluster problem and is a provisioning one. Failing at startup puts
the error where somebody is already looking.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Final

import uvicorn

from config.constants.executor import (
    DEFAULT_EXECUTOR_USER,
    NINJASRE_EXECUTOR_IDENTITY_ENV,
    NINJASRE_EXECUTOR_USER_ENV,
)
from gateway.executor.app import build_executor_app
from gateway.executor.openssh import OpenSshRunner
from platform.observability.logging import get_logger

_LOGGER: Final = get_logger(__name__)

#: Re-exported so this module reads as one piece; the names themselves are
#: declared where every environment name in this repository is declared.
IDENTITY_ENV: Final = NINJASRE_EXECUTOR_IDENTITY_ENV
USER_ENV: Final = NINJASRE_EXECUTOR_USER_ENV
DEFAULT_USER: Final = DEFAULT_EXECUTOR_USER


class NoIdentity(RuntimeError):
    """The executor was started without a key to reach anything with."""


def _runner() -> OpenSshRunner:
    """Return the transport this executor was provisioned with.

    Raises:
        NoIdentity: no identity was named, or the file is not there. Refused at
            startup rather than at the first request, because an executor with
            no key answers every request as an unreachable node — which reads as
            a cluster problem and is a provisioning one.
    """
    identity = os.environ.get(IDENTITY_ENV, "").strip()
    if not identity:
        raise NoIdentity(
            f"{IDENTITY_ENV} names the SSH identity this executor authenticates with, "
            f"and nothing set it. An executor with no identity cannot reach a node."
        )
    if not Path(identity).is_file():
        raise NoIdentity(f"{IDENTITY_ENV} names a path that is not a file")

    return OpenSshRunner(
        user=os.environ.get(USER_ENV, "").strip() or DEFAULT_USER, identity=identity
    )


def main(argv: list[str] | None = None) -> int:
    """Serve the executor, or say why it cannot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8440)
    arguments = parser.parse_args(argv)

    try:
        runner = _runner()
    except NoIdentity as refused:
        print(f"executor: {refused}", file=sys.stderr)  # noqa: T201 — talking to a person
        return 1

    _LOGGER.info("executor.startup", host=arguments.host, port=arguments.port)
    uvicorn.run(
        build_executor_app(runner=runner),
        host=arguments.host,
        port=arguments.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
