"""The sidecar configuration, generated from the allow-list rather than written.

Envoy is here because application-level egress restriction is cooperative, and a
cooperative control is not a control. The capability's own process cannot be
trusted to honour ``HTTPS_PROXY``: it is running code an LLM selected, over data
an attacker may have written. Putting the allow-list in a separate process in
the same network namespace, with a ``NetworkPolicy`` making that process the only
way out, is what turns "should not reach that host" into "cannot".

The configuration has exactly three moving parts.

**A cluster per allowed host.** Each declared host becomes a cluster with strict
DNS and its own upstream. That is what makes an allow-list entry mean something
at connection time rather than at request-parse time.

**A blackhole as the default route.** The last virtual host matches ``*`` and
answers with a fixed 403 and a body naming the deployment's allow-list. Not a
connection reset: a capability that gets a reset reports "the network is broken"
and the operator spends an hour on the wrong thing, where a 403 saying "this host
is not allow-listed" ends the question.

**An access log of the refusals.** A blocked attempt has to be audited with
its target, and the sidecar is the only component that sees the attempt at all —
the capability's own process never learns whether the host resolved.

The list itself is never written here. It comes from ``EgressPolicy``, which is
the union of the ``InjectionRule.hosts`` of the team's configured integrations,
which is the same tuple the credential proxy checks against. Adding an
integration widens both by construction; there is no second list to update.
"""

from __future__ import annotations

import json
import re
from typing import Any

from config.constants.security import (
    SANDBOX_ENVOY_ADMIN_PORT,
    SANDBOX_ENVOY_LISTENER_PORT,
)
from platform.sandbox.spec import EgressPolicy

#: The refusal a capability sees when it addresses a host nobody declared.
BLOCKED_EGRESS_STATUS = 403

#: What Envoy calls the route that matches everything left over. Named rather
#: than anonymous so the access log line for a refusal is greppable.
BLACKHOLE_ROUTE_NAME = "ninjasre-egress-blocked"

#: Where the sidecar writes its access log. Standard error rather than a file:
#: the pod is ephemeral and a file inside it is a log nobody will ever read.
ACCESS_LOG_PATH = "/dev/stderr"


def config_map_name(sandbox_id: str) -> str:
    """Return the name of the ConfigMap holding one sandbox's Envoy configuration."""
    return f"ninjasre-egress-{sandbox_id}"


def cluster_name(host: str) -> str:
    """Return the Envoy cluster name for ``host``.

    Envoy names may not contain a dot in every version's validation, and a
    deterministic transform is what lets a test assert which cluster a route
    points at without reproducing the sanitisation.
    """
    return "host_" + re.sub(r"[^a-zA-Z0-9]+", "_", host.lower()).strip("_")


def bootstrap(policy: EgressPolicy, *, sandbox_id: str) -> dict[str, Any]:
    """Return the Envoy bootstrap enforcing ``policy`` for one sandbox.

    Everything the sandbox may reach is a cluster; everything else falls to the
    blackhole. The proxy is a cluster like any vendor, which is deliberate — it
    keeps "the proxy is reachable" a property of the same list rather than a
    special case that could be true when the list is wrong.
    """
    hosts = policy.reachable()
    return {
        "admin": {
            # Loopback only. An admin interface a sandbox container could reach
            # is an admin interface that can delete the allow-list, and the two
            # containers share a network namespace.
            "address": {
                "socket_address": {"address": "127.0.0.1", "port_value": SANDBOX_ENVOY_ADMIN_PORT}
            }
        },
        "static_resources": {
            "listeners": [_listener(hosts, sandbox_id=sandbox_id)],
            "clusters": [
                _cluster(host, port=policy.proxy_port if host == policy.proxy_host else 443)
                for host in hosts
            ],
        },
    }


def _listener(hosts: tuple[str, ...], *, sandbox_id: str) -> dict[str, Any]:
    """Return the listener every packet leaving the pod arrives at."""
    return {
        "name": "egress",
        "address": {
            "socket_address": {"address": "0.0.0.0", "port_value": SANDBOX_ENVOY_LISTENER_PORT}
        },
        "filter_chains": [
            {
                "filters": [
                    {
                        "name": "envoy.filters.network.http_connection_manager",
                        "typed_config": {
                            "@type": (
                                "type.googleapis.com/envoy.extensions.filters.network."
                                "http_connection_manager.v3.HttpConnectionManager"
                            ),
                            "stat_prefix": "ninjasre_egress",
                            "access_log": [
                                {
                                    "name": "envoy.access_loggers.file",
                                    "typed_config": {
                                        "@type": (
                                            "type.googleapis.com/envoy.extensions."
                                            "access_loggers.file.v3.FileAccessLog"
                                        ),
                                        "path": ACCESS_LOG_PATH,
                                        "log_format": {
                                            "json_format": {
                                                "sandbox": sandbox_id,
                                                "host": "%REQ(:AUTHORITY)%",
                                                "path": "%REQ(:PATH)%",
                                                "route": "%ROUTE_NAME%",
                                                "status": "%RESPONSE_CODE%",
                                            }
                                        },
                                    },
                                }
                            ],
                            "http_filters": [
                                {
                                    "name": "envoy.filters.http.router",
                                    "typed_config": {
                                        "@type": (
                                            "type.googleapis.com/envoy.extensions.filters."
                                            "http.router.v3.Router"
                                        )
                                    },
                                }
                            ],
                            "route_config": {
                                "name": "egress",
                                "virtual_hosts": [
                                    *(_virtual_host(host) for host in hosts),
                                    _blackhole(hosts),
                                ],
                            },
                        },
                    }
                ]
            }
        ],
    }


def _virtual_host(host: str) -> dict[str, Any]:
    """Return the route that lets one allow-listed host through."""
    return {
        "name": cluster_name(host),
        "domains": [host, f"{host}:*"],
        "routes": [
            {
                "name": f"allow_{cluster_name(host)}",
                "match": {"prefix": "/"},
                "route": {"cluster": cluster_name(host)},
            }
        ],
    }


def _blackhole(hosts: tuple[str, ...]) -> dict[str, Any]:
    """Return the catch-all that refuses everything the allow-list did not name."""
    allowed = ", ".join(hosts) if hosts else "nothing"
    return {
        "name": BLACKHOLE_ROUTE_NAME,
        "domains": ["*"],
        "routes": [
            {
                "name": BLACKHOLE_ROUTE_NAME,
                "match": {"prefix": "/"},
                "direct_response": {
                    "status": BLOCKED_EGRESS_STATUS,
                    "body": {
                        "inline_string": (
                            "This host is not on the deployment's egress allow-list. "
                            f"Reachable: {allowed}."
                        )
                    },
                },
            }
        ],
    }


def _cluster(host: str, *, port: int) -> dict[str, Any]:
    """Return the upstream one allow-listed host resolves to."""
    return {
        "name": cluster_name(host),
        "type": "STRICT_DNS",
        "connect_timeout": "5s",
        "load_assignment": {
            "cluster_name": cluster_name(host),
            "endpoints": [
                {
                    "lb_endpoints": [
                        {
                            "endpoint": {
                                "address": {"socket_address": {"address": host, "port_value": port}}
                            }
                        }
                    ]
                }
            ],
        },
    }


def config_map(policy: EgressPolicy, *, sandbox_id: str, namespace: str) -> dict[str, Any]:
    """Return the ConfigMap the sidecar reads its configuration from.

    YAML rather than JSON in the ``data`` value because Envoy accepts both and
    an operator debugging a refusal reads this by hand — the whole reason the
    blackhole answers with a message rather than a reset.
    """
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": config_map_name(sandbox_id), "namespace": namespace},
        "data": {"envoy.yaml": json.dumps(bootstrap(policy, sandbox_id=sandbox_id), indent=2)},
    }


def permitted_hosts(bootstrap_config: dict[str, Any]) -> tuple[str, ...]:
    """Return the hosts a generated bootstrap actually lets through.

    Read back out of the configuration rather than from the policy it was built
    from. A test that asserted against the policy would prove the policy agrees
    with itself; this proves the *sidecar* would.
    """
    listeners = bootstrap_config["static_resources"]["listeners"]
    manager = listeners[0]["filter_chains"][0]["filters"][0]["typed_config"]
    return tuple(
        virtual_host["domains"][0]
        for virtual_host in manager["route_config"]["virtual_hosts"]
        if virtual_host["name"] != BLACKHOLE_ROUTE_NAME
    )


__all__ = [
    "ACCESS_LOG_PATH",
    "BLACKHOLE_ROUTE_NAME",
    "BLOCKED_EGRESS_STATUS",
    "bootstrap",
    "cluster_name",
    "config_map",
    "config_map_name",
    "permitted_hosts",
]
