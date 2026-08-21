"""ClickUp, end to end: capability, client, proxy, injection, vendor.

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
    "api_key": "ninjasre-scenario-key-000000",
    "list_id": "900100",
}


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="clickup-issue-statistics",
    integration="clickup",
    capability="clickup_issue_statistics",
    arguments={"query": "", "start": "", "end": "", "group_by": "status.status"},
    responses=(
        json_response(
            {
                "tasks": [
                    {"id": "t1", "status": {"status": "in progress"}},
                    {"id": "t2", "status": {"status": "in progress"}},
                    {"id": "t3", "status": {"status": "complete"}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/api/v2/list/900100/task",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="clickup-recent-issues",
    integration="clickup",
    capability="clickup_recent_issues",
    arguments={"query": "", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {"tasks": [{"id": "t1", "name": "cart 500s", "status": {"status": "in progress"}}]}
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from ClickUp",
    expected_paths=("/api/v2/list/900100/task",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]
