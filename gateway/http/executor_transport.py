"""Carrying one execution request to the executor over HTTP.

Thin on purpose. Everything that decides whether a command may run lives in the
executor, behind the allowlist; this only has to reach it and not lose which of
the four outcomes came back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import httpx

from config.constants.executor import NODE_COMMAND_TIMEOUT_SECONDS

#: Where the executor listens for one command.
EXECUTE_PATH: Final = "/execute"


@dataclass(frozen=True, slots=True)
class HttpExecutorTransport:
    """The executor, reached over HTTP."""

    base_url: str
    timeout_seconds: float = NODE_COMMAND_TIMEOUT_SECONDS

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the executor's answer, or raise if it did not give one."""
        async with httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"), timeout=self.timeout_seconds
        ) as client:
            answer = await client.post(EXECUTE_PATH, json=payload)
            answer.raise_for_status()
            body: Any = answer.json()
        return body if isinstance(body, dict) else {}


__all__ = ["EXECUTE_PATH", "HttpExecutorTransport"]
