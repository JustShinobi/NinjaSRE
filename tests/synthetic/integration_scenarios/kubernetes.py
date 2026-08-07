"""Kubernetes, end to end: capability, client, proxy, bearer token, API server.

The first scenario is the one that matters most in practice: an `OOMKilled`
warning event reaching a finding with the reason intact. That string is what
turns "the pod restarted" into a root cause, and it travels through four layers
between the API server and the summary — any of which could drop it while
everything still returns a result.

The second walks the continue token, which Kubernetes leaves as an empty string
on the last page in exactly the way CloudWatch does, and matches replica sets by
the deployment's own selector rather than by name prefix — the thing that keeps
`checkout-canary`'s rollout history out of `checkout`'s investigation.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

CREDENTIAL: Final[dict[str, str]] = {
    "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IiJ9.scenario",
    "cluster": "prod",
}

WORKLOAD_EVENTS: Final = IntegrationScenario(
    key="kubernetes-workload-events",
    integration="kubernetes",
    capability="kubernetes_workload_events",
    arguments={"namespace": "production", "object_name": "checkout-7f4c", "limit": 10},
    responses=(
        json_response(
            {
                "items": [
                    {
                        "reason": "OOMKilled",
                        "type": "Warning",
                        "message": "Container checkout exceeded its memory limit of 512Mi",
                        "count": 3,
                        "involvedObject": {"name": "checkout-7f4c"},
                        "lastTimestamp": "2026-08-07T11:58:02Z",
                    },
                    {
                        "reason": "BackOff",
                        "type": "Warning",
                        "message": "Back-off restarting failed container",
                        "count": 5,
                        "involvedObject": {"name": "checkout-7f4c"},
                        "lastTimestamp": "2026-08-07T11:59:44Z",
                    },
                ],
                "metadata": {"continue": ""},
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="BackOff, OOMKilled",
)

ROLLOUT_HISTORY: Final = IntegrationScenario(
    key="kubernetes-rollout-history",
    integration="kubernetes",
    capability="kubernetes_rollout_history",
    arguments={"deployment": "checkout", "namespace": "production"},
    responses=(
        json_response(
            {
                "kind": "Deployment",
                "metadata": {"name": "checkout"},
                "spec": {"selector": {"matchLabels": {"app": "checkout"}}},
            }
        ),
        json_response(
            {
                "items": [
                    {
                        "metadata": {
                            "name": "checkout-5d9f",
                            "creationTimestamp": "2026-08-07T11:54:00Z",
                            "annotations": {"deployment.kubernetes.io/revision": "412"},
                        },
                        "spec": {
                            "template": {
                                "spec": {"containers": [{"image": "checkout:2026.8.7-a1"}]}
                            }
                        },
                        "status": {"replicas": 4},
                    },
                    {
                        "metadata": {
                            "name": "checkout-4c1a",
                            "creationTimestamp": "2026-08-05T09:10:00Z",
                            "annotations": {"deployment.kubernetes.io/revision": "411"},
                        },
                        "spec": {
                            "template": {
                                "spec": {"containers": [{"image": "checkout:2026.8.5-f3"}]}
                            }
                        },
                        "status": {"replicas": 0},
                    },
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="checkout is on revision 412",
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (WORKLOAD_EVENTS, ROLLOUT_HISTORY)

__all__ = ["CREDENTIAL", "ROLLOUT_HISTORY", "SCENARIOS", "WORKLOAD_EVENTS"]
