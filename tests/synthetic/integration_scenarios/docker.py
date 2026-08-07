"""Docker, end to end: capability, client, proxy, injection, vendor.

The seventh parity artefact. Everything else about an integration can look
finished while nothing exercises the path a real call takes — and the first
thing to notice that is the investigation which needed it.

So these drive the whole path: the registered capability, the client, the real
credential proxy with this integration's own injection rule, and a scripted
vendor on the far side. Nothing is mocked between the tool and the wire, which
is what makes a renamed response field fail here rather than at 03:00.
"""

from __future__ import annotations

from typing import Final

from tests.synthetic.integration_scenarios import IntegrationScenario, json_response

#: Not a real credential. The suite asserts that none of these values reaches a
#: client, a result, or a trace, which is the property SC-003 is about.
CREDENTIAL: Final[dict[str, str]] = {
    "token": "ninjasre-scenario-token-000000",
}


RESOURCE_INVENTORY: Final = IntegrationScenario(
    key="docker-resource-inventory",
    integration="docker",
    capability="docker_resource_inventory",
    arguments={"kind": "", "start": "", "end": "", "group_by": "State"},
    responses=(
        json_response(
            [
                {"Names": ["/checkout"], "State": "running"},
                {"Names": ["/payments"], "State": "running"},
                {"Names": ["/reports"], "State": "exited"},
            ]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 resources across",
    expected_paths=("/containers/json",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="docker-recent-changes",
    integration="docker",
    capability="docker_recent_changes",
    arguments={"kind": "", "start": "1754499600", "end": "1754503200", "limit": 10},
    responses=(
        json_response(
            [{"Action": "die", "Actor": {"Attributes": {"name": "reports"}}, "time": 1754503600}]
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from Docker",
    expected_paths=("/events",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (RESOURCE_INVENTORY, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "RESOURCE_INVENTORY", "RECENT_CHANGES"]
