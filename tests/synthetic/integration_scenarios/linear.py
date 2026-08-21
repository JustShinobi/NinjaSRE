"""Linear, end to end: capability, client, proxy, injection, vendor.

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


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="linear-issue-statistics",
    integration="linear",
    capability="linear_issue_statistics",
    arguments={"query": "", "start": "", "end": "", "group_by": "state.name"},
    responses=(
        json_response(
            {
                "data": {
                    "issues": {
                        "nodes": [
                            {"identifier": "CHK-1", "state": {"name": "In Progress"}},
                            {"identifier": "CHK-2", "state": {"name": "In Progress"}},
                            {"identifier": "CHK-3", "state": {"name": "Done"}},
                        ]
                    }
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/graphql",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="linear-recent-issues",
    integration="linear",
    capability="linear_recent_issues",
    arguments={"query": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "identifier": "CHK-1",
                                "title": "cart 500s",
                                "state": {"name": "In Progress"},
                            }
                        ]
                    }
                }
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Linear",
    expected_paths=("/graphql",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]
