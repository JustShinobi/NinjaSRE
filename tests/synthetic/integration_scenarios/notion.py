"""Notion, end to end: capability, client, proxy, injection, vendor.

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
    "token": "ninjasre-scenario-key-000000",
    "api_version": "2022-06-28",
}


ISSUE_STATISTICS: Final = IntegrationScenario(
    key="notion-issue-statistics",
    integration="notion",
    capability="notion_issue_statistics",
    arguments={"query": "checkout runbook", "start": "", "end": "", "group_by": "object"},
    responses=(
        json_response(
            {
                "results": [
                    {"id": "p1", "object": "page"},
                    {"id": "p2", "object": "page"},
                    {"id": "d1", "object": "database"},
                ],
                "next_cursor": None,
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/v1/search",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="notion-recent-issues",
    integration="notion",
    capability="notion_recent_issues",
    arguments={"query": "checkout runbook", "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "results": [
                    {"id": "p1", "object": "page", "last_edited_time": "2026-02-01T09:00:00Z"}
                ],
                "next_cursor": None,
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Notion",
    expected_paths=("/v1/search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]
