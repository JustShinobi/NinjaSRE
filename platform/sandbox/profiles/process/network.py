"""Egress for the profile that has the least to work with, stated honestly.

The ``process`` profile has two mechanisms available and they do not compose.

**A loopback-only network namespace** is real isolation: the child gets an
interface list containing ``lo`` and nothing else, and no amount of cooperation
from the capability can produce a packet that leaves the host. It is only usable
when two things hold — the kernel permits an unprivileged process to unshare a
user and network namespace, and the credential proxy is on loopback, because a
namespace with only ``lo`` in it cannot reach a proxy that is anywhere else.
That combination is exactly the local development case the profile exists for.

**Proxy-only routing** is what remains otherwise: a minimal environment naming
the proxy for every scheme, with nothing else in it. That is cooperative. A
capability that opens its own socket is not stopped by it, and this module does
not pretend otherwise — ``EgressPlan.strength`` says ``BEST_EFFORT`` and the
startup report says it out loud.

The probe is a real one. Asking "does this kernel allow unprivileged user
namespaces" by reading a sysctl gets the answer wrong on hosts where the sysctl
does not exist and on containers where seccomp blocks the syscall regardless. So
the probe forks a child and calls ``unshare``, which is the only question that
matters and costs about a millisecond, once per process.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache

from config.constants.security import (
    SANDBOX_HTTP_PROXY_ENV,
    SANDBOX_HTTPS_PROXY_ENV,
    SANDBOX_NO_PROXY_ENV,
)
from platform.sandbox.selection import GuaranteeStrength
from platform.sandbox.spec import EgressPolicy


@dataclass(frozen=True, slots=True)
class EgressPlan:
    """How one sandbox's egress will actually be constrained.

    Returned before anything is spawned so the decision is inspectable — a test
    asserts what will be enforced rather than inferring it from whether a
    connection happened to fail, and the health report can say which mechanism a
    running deployment ended up with.
    """

    mechanism: str
    strength: GuaranteeStrength
    isolate_network_namespace: bool
    environment: dict[str, str]
    allowed_hosts: tuple[str, ...]

    def permits(self, host: str) -> bool:
        """Return whether ``host`` is one this sandbox may address."""
        return host.lower() in {allowed.lower() for allowed in self.allowed_hosts}


def plan_egress(policy: EgressPolicy, *, namespace_available: bool | None = None) -> EgressPlan:
    """Return how ``policy`` will be enforced for a ``process``-profile sandbox.

    The namespace is used only when the proxy is on loopback. Isolating a
    sandbox from the network *including* from the thing that authenticates its
    calls would be strictly stronger and completely useless, and choosing
    "stronger" over "works" is how an isolation layer gets turned off.
    """
    available = (
        namespace_available if namespace_available is not None else network_namespace_available()
    )
    isolate = available and policy.proxy_is_loopback

    environment = {
        SANDBOX_HTTP_PROXY_ENV: policy.proxy_url,
        SANDBOX_HTTPS_PROXY_ENV: policy.proxy_url,
        # Only the proxy host itself is exempt from being proxied. Everything
        # else, allow-listed or not, goes through the proxy — which is what
        # makes the proxy's own allow-list the second enforcement point rather
        # than a duplicate of this one.
        SANDBOX_NO_PROXY_ENV: policy.proxy_host,
    }

    if isolate:
        return EgressPlan(
            mechanism="loopback-only network namespace, proxy on loopback",
            strength=GuaranteeStrength.ENFORCED,
            isolate_network_namespace=True,
            environment=environment,
            allowed_hosts=policy.reachable(),
        )
    return EgressPlan(
        mechanism="proxy-only routing (cooperative)",
        strength=GuaranteeStrength.BEST_EFFORT,
        isolate_network_namespace=False,
        environment=environment,
        allowed_hosts=policy.reachable(),
    )


@lru_cache(maxsize=1)
def network_namespace_available() -> bool:
    """Return whether this host lets an unprivileged process unshare a network namespace.

    Cached for the life of the process. The answer is a property of the kernel
    and its seccomp profile, neither of which changes under a running
    deployment, and the probe costs a fork.
    """
    if sys.platform == "win32":
        return False
    return _probe_unshare()


def _probe_unshare() -> bool:
    """Fork a child, have it try the unshare, and report whether it worked.

    ``os._exit`` in the child rather than a return: the child is a copy of a
    process holding an event loop, open sockets, and a test runner's state, and
    unwinding any of that would run handlers twice.
    """
    from platform.sandbox.profiles.process.limits_posix import _unshare_network

    try:
        pid = os.fork()
    except OSError:
        return False

    if pid == 0:  # pragma: no cover — the child never returns to the test runner
        try:
            _unshare_network()
        except OSError:
            os._exit(1)
        except Exception:  # noqa: BLE001 — a probe must not raise out of a fork
            os._exit(1)
        os._exit(0)

    try:
        _, status = os.waitpid(pid, 0)
    except OSError:
        return False
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


__all__ = [
    "EgressPlan",
    "network_namespace_available",
    "plan_egress",
]
