"""What the node executor is called, and the bounds it runs inside.

The executor is the one process in this system that holds an SSH identity, so
the numbers here are the numbers that keep one unreachable node from becoming a
request nobody returns from.
"""

from __future__ import annotations

from typing import Final

#: What the capability that reads from a node is called. Named after what a
#: caller gets rather than after SSH, because how the reading is fetched is an
#: implementation detail an investigation should never depend on.
NODE_COMMAND_TOOL_NAME: Final[str] = "run_on_node"

#: Where the executor listens, as a deployment names it. An environment
#: variable rather than a configuration field: a deployment that has an
#: executor decided so when it was provisioned, and the address is a fact
#: about the deployment rather than about the estate it watches.
NINJASRE_NODE_EXECUTOR_URL_ENV: Final[str] = "NINJASRE_NODE_EXECUTOR_URL"

#: Where the executor's own SSH identity is, and who it authenticates as.
#: Environment rather than configuration: both are facts about how that
#: process was provisioned, and nothing about the estate it reaches.
NINJASRE_EXECUTOR_IDENTITY_ENV: Final[str] = "NINJASRE_EXECUTOR_IDENTITY"
NINJASRE_EXECUTOR_USER_ENV: Final[str] = "NINJASRE_EXECUTOR_USER"

#: Who the identity authenticates as when nothing names one. Declared rather
#: than left to the invoking user, so a mistake is a refusal rather than a
#: root session.
DEFAULT_EXECUTOR_USER: Final[str] = "ninjasre"

#: How long one command may take before the node is reported as unreachable. A
#: node that has stopped answering must become a finding rather than a request
#: held open.
NODE_COMMAND_TIMEOUT_SECONDS: Final[float] = 20.0

#: How long the executor waits to open a connection at all. Shorter than the
#: command budget: a node that will not accept a connection is not going to
#: start halfway through one.
NODE_CONNECT_TIMEOUT_SECONDS: Final[int] = 10

__all__ = [
    "DEFAULT_EXECUTOR_USER",
    "NINJASRE_EXECUTOR_IDENTITY_ENV",
    "NINJASRE_EXECUTOR_USER_ENV",
    "NINJASRE_NODE_EXECUTOR_URL_ENV",
    "NODE_COMMAND_TIMEOUT_SECONDS",
    "NODE_COMMAND_TOOL_NAME",
    "NODE_CONNECT_TIMEOUT_SECONDS",
]
