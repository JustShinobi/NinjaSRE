"""Jira, end to end: capability, client, proxy, injection, vendor.

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
}


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="jira-issue-statistics",
    integration="jira",
    capability="jira_issue_statistics",
    arguments={"query": "project = CHK", "start": "", "end": "", "group_by": "fields.status.name"},
    responses=(
        json_response(
            {
                "issues": [
                    {"key": "CHK-1", "fields": {"status": {"name": "In Progress"}}},
                    {"key": "CHK-2", "fields": {"status": {"name": "In Progress"}}},
                    {"key": "CHK-3", "fields": {"status": {"name": "Done"}}},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/rest/api/3/search/jql",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="jira-recent-issues",
    integration="jira",
    capability="jira_recent_issues",
    arguments={"query": "project = CHK AND status != Done", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "issues": [
                    {
                        "key": "CHK-1",
                        "fields": {"summary": "cart 500s", "status": {"name": "In Progress"}},
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Jira",
    expected_paths=("/rest/api/3/search/jql",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]
