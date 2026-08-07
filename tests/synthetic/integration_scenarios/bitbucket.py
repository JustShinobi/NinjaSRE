"""Bitbucket, end to end: capability, client, proxy, injection, vendor.

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
    "username": "ninjasre-scenario",
    "password": "ninjasre-scenario-secret",
    "workspace": "acme",
}


CHANGE_STATISTICS: Final = IntegrationScenario(
    key="bitbucket-change-statistics",
    integration="bitbucket",
    capability="bitbucket_change_statistics",
    arguments={"repository": "", "start": "", "end": "", "group_by": "language"},
    responses=(
        json_response(
            {
                "values": [
                    {"name": "checkout", "language": "python"},
                    {"name": "payments", "language": "python"},
                    {"name": "web", "language": "typescript"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 commits across",
    expected_paths=("/2.0/repositories/acme",),
)


RECENT_CHANGES: Final = IntegrationScenario(
    key="bitbucket-recent-changes",
    integration="bitbucket",
    capability="bitbucket_recent_changes",
    arguments={"repository": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "values": [
                    {"name": "checkout", "language": "python", "updated_on": "2026-08-07T11:50:00Z"}
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 changes from Bitbucket",
    expected_paths=("/2.0/repositories/acme",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (CHANGE_STATISTICS, RECENT_CHANGES)

__all__ = ["CREDENTIAL", "SCENARIOS", "CHANGE_STATISTICS", "RECENT_CHANGES"]
