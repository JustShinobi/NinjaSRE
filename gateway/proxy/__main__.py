"""The credential proxy's process: ``python -m gateway.proxy``.

Deliberately does not migrate. The application owns the schema — one process
applying migrations under the advisory lock is the design (FR-007), and a proxy
that also migrated would be a second writer racing it for no benefit. What it
does do is verify the encryption key opens what is stored, because a proxy that
starts with the wrong key is a deployment where every authenticated call fails
during the first incident that needs one.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

import uvicorn

from config.constants.surfaces import DEFAULT_API_HOST, DEFAULT_CREDENTIAL_PROXY_PORT
from gateway.proxy.composition import build_proxy_app
from platform.credentials.errors import VaultKeyMismatch
from platform.observability.logging import get_logger
from platform.startup.errors import StartupError

_LOGGER = get_logger(__name__)

#: Distinct from a crash, so a supervisor does not restart a typo forever.
CONFIGURATION_EXIT = 3


async def _serve(host: str, port: int) -> None:
    """Compose, check the key, and serve — all on one event loop."""
    app, store = build_proxy_app()

    health = await store.health()
    if health.undecryptable_credentials:
        raise VaultKeyMismatch(health.undecryptable_credentials)

    _LOGGER.info(
        "proxy.startup",
        integrations=len(app.engine.rules.integrations()),
    )

    try:
        await uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None)).serve()
    finally:
        await store.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the credential proxy. Returns the process exit code."""
    import argparse

    parser = argparse.ArgumentParser(prog="ninjasre-proxy", description=__doc__)
    parser.add_argument("--host", default=DEFAULT_API_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_CREDENTIAL_PROXY_PORT)
    arguments = parser.parse_args(argv)

    try:
        asyncio.run(_serve(arguments.host, arguments.port))
    except (StartupError, VaultKeyMismatch) as error:
        _LOGGER.error("proxy.refused_to_start", reason=str(error))
        print(str(error), file=sys.stderr)  # noqa: T201 — the operator is reading a terminal
        return CONFIGURATION_EXIT
    return 0


if __name__ == "__main__":  # pragma: no cover — the container's entrypoint
    raise SystemExit(main())


__all__ = ["CONFIGURATION_EXIT", "main"]
