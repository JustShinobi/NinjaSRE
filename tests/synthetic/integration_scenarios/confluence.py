"""Confluence, end to end: capability, client, proxy, injection, vendor.

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
    key="confluence-issue-statistics",
    integration="confluence",
    capability="confluence_issue_statistics",
    arguments={"query": 'text ~ "cart"', "start": "", "end": "", "group_by": "type"},
    responses=(
        json_response(
            {
                "results": [
                    {"id": "1", "title": "Checkout runbook", "type": "page"},
                    {"id": "2", "title": "Cart limits", "type": "page"},
                    {"id": "3", "title": "Old notes", "type": "blogpost"},
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="3 issues across",
    expected_paths=("/wiki/rest/api/content/search",),
)


RECENT_ISSUES: Final = IntegrationScenario(
    key="confluence-recent-issues",
    integration="confluence",
    capability="confluence_recent_issues",
    arguments={"query": 'text ~ "cart"', "start": "", "end": "", "limit": 10},
    responses=(
        json_response(
            {
                "results": [
                    {
                        "id": "1",
                        "title": "Checkout runbook",
                        "version": {"when": "2026-02-01T09:00:00Z"},
                    }
                ]
            }
        ),
    ),
    credential=CREDENTIAL,
    expected_summary="1 issues from Confluence",
    expected_paths=("/wiki/rest/api/content/search",),
)

SCENARIOS: Final[tuple[IntegrationScenario, ...]] = (ISSUE_STATISTICS, RECENT_ISSUES)

__all__ = ["CREDENTIAL", "SCENARIOS", "ISSUE_STATISTICS", "RECENT_ISSUES"]
